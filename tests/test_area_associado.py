"""Testes da área do associado: primeiro acesso, termo de dados e imagem, foto e comprovantes."""
import io
import os
from datetime import date, datetime, timedelta

import pytest
from PIL import Image

from app import create_app, db
from app.area_associado import gerar_codigo_acesso, pasta_fotos
from app.models import Associado, Mensalidade, Usuario
from app.regras import competencia_atual, garantir_mensalidades
from app import termo

CPF_ANA = "52998224725"
CPF_MARIA = "39053344705"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'area.db'}",
    })
    app.instance_path = str(tmp_path)
    with app.app_context():
        db.create_all()
        u = Usuario(nome="Equipe Teste", login="equipe")
        u.definir_senha("senha-forte")
        db.session.add(u)
        for numero, nome, cpf in [("0142", "Ana Teste", CPF_ANA), ("0057", "Maria Teste", CPF_MARIA)]:
            a = Associado(numero_socio=numero, nome=nome, cpf=cpf, categoria="regular",
                          data_inscricao=date.today() - timedelta(days=200), celular="11999990000")
            a.criar_checklist()
            db.session.add(a)
        db.session.commit()
    yield app


def ana():
    return db.session.execute(db.select(Associado).filter_by(cpf=CPF_ANA)).scalar_one()


def foto_bytes(largura=1200, altura=800, formato="JPEG"):
    buffer = io.BytesIO()
    Image.new("RGB", (largura, altura), (40, 60, 140)).save(buffer, formato)
    buffer.seek(0)
    return buffer


def codigo_para(app, cpf=CPF_ANA):
    with app.app_context():
        a = db.session.execute(db.select(Associado).filter_by(cpf=cpf)).scalar_one()
        codigo = gerar_codigo_acesso(a)
        db.session.commit()
        return codigo


def primeiro_acesso(cliente, codigo, cpf="529.982.247-25", senha="minhasenha"):
    return cliente.post("/associado/primeiro-acesso", data={
        "cpf": cpf, "codigo": codigo.lower(), "senha": senha, "confirmar": senha,
    })


def logado_com_termo(app, imagem=True):
    c = app.test_client()
    primeiro_acesso(c, codigo_para(app))
    dados = {"aceite_dados": "1"}
    if imagem:
        dados["aceite_imagem"] = "1"
    c.post("/associado/termo", data=dados)
    return c


def test_sem_login_vai_para_entrar(app):
    r = app.test_client().get("/associado/")
    assert r.status_code == 302 and "/associado/entrar" in r.headers["Location"]


def test_primeiro_acesso_com_codigo_cria_senha_e_pede_termo(app):
    c = app.test_client()
    r = primeiro_acesso(c, codigo_para(app))
    assert r.status_code == 302 and "/associado/termo" in r.headers["Location"]
    with app.app_context():
        a = ana()
        assert a.conferir_senha("minhasenha")
        assert a.codigo_acesso is None  # código só vale uma vez
    # enquanto não aceitar o termo, qualquer página leva para o termo
    assert "/associado/termo" in c.get("/associado/").headers["Location"]


def test_codigo_errado_ou_vencido_nao_entra(app):
    c = app.test_client()
    codigo_para(app)
    r = primeiro_acesso(c, "ZZZZZZ")
    assert "inválido" in r.get_data(as_text=True)
    with app.app_context():
        a = ana()
        codigo = gerar_codigo_acesso(a)
        a.codigo_expira_em = datetime.now() - timedelta(minutes=1)
        db.session.commit()
    r = primeiro_acesso(c, codigo)
    assert "vencido" in r.get_data(as_text=True)


def test_bloqueio_depois_de_5_tentativas(app):
    c = app.test_client()
    codigo = codigo_para(app)
    for _ in range(5):
        c.post("/associado/entrar", data={"cpf": CPF_ANA, "senha": "errada"})
    r = primeiro_acesso(c, codigo)  # mesmo com o código certo, fica bloqueado 15 min
    assert "Muitas tentativas" in r.get_data(as_text=True)


def test_entrar_com_senha_depois_do_primeiro_acesso(app):
    c = logado_com_termo(app)
    c.post("/associado/sair")
    assert c.get("/associado/").status_code == 302
    r = c.post("/associado/entrar", data={"cpf": "529.982.247-25", "senha": "minhasenha"})
    assert r.headers["Location"].endswith("/associado/")
    pagina = c.get("/associado/").get_data(as_text=True)
    assert "Nº 0142" in pagina and "Carteirinha digital" in pagina


def test_termo_exige_aceite_dos_dados(app):
    c = app.test_client()
    primeiro_acesso(c, codigo_para(app))
    r = c.post("/associado/termo", data={"aceite_imagem": "1"})
    assert "é preciso aceitar" in r.get_data(as_text=True)
    with app.app_context():
        assert ana().termo_aceito_em is None
    c.post("/associado/termo", data={"aceite_dados": "1"})
    with app.app_context():
        a = ana()
        assert a.termo_aceito_em and a.termo_versao == termo.VERSAO
        assert a.imagem_autorizada_em is None


def test_foto_sem_autorizacao_de_imagem_e_bloqueada(app):
    c = logado_com_termo(app, imagem=False)
    r = c.post("/associado/foto", data={"foto": (foto_bytes(), "eu.jpg")}, content_type="multipart/form-data")
    assert "/associado/termo" in r.headers["Location"]
    with app.app_context():
        assert ana().foto is None


def test_foto_e_recortada_e_salva_em_jpg_600(app):
    c = logado_com_termo(app)
    c.post("/associado/foto", data={"foto": (foto_bytes(formato="PNG"), "eu.png")}, content_type="multipart/form-data")
    with app.app_context():
        a = ana()
        assert a.foto and a.foto.endswith(".jpg")
        caminho = os.path.join(pasta_fotos(), a.foto)
        with Image.open(caminho) as img:
            assert img.format == "JPEG" and img.size == (600, 600)
    assert c.get("/associado/foto.jpg").status_code == 200


def test_arquivo_que_nao_e_imagem_e_recusado(app):
    c = logado_com_termo(app)
    c.post("/associado/foto", data={"foto": (io.BytesIO(b"nao sou imagem"), "x.jpg")}, content_type="multipart/form-data")
    with app.app_context():
        assert ana().foto is None


def test_retirar_autorizacao_apaga_a_foto(app):
    c = logado_com_termo(app)
    c.post("/associado/foto", data={"foto": (foto_bytes(), "eu.jpg")}, content_type="multipart/form-data")
    with app.app_context():
        caminho = os.path.join(pasta_fotos(), ana().foto)
    assert os.path.exists(caminho)
    c.post("/associado/termo", data={"aceite_dados": "1"})  # desmarcou a imagem
    with app.app_context():
        a = ana()
        assert a.foto is None and a.imagem_autorizada_em is None
    assert not os.path.exists(caminho)


def test_comprovante_enviado_pelo_associado_fica_em_analise(app):
    c = logado_com_termo(app)
    with app.app_context():
        garantir_mensalidades(competencia_atual())
        m = db.session.execute(db.select(Mensalidade).filter_by(associado_id=ana().id, status="aberta")).scalars().first()
        mid = m.id
    c.post(f"/associado/mensalidades/{mid}/comprovante",
           data={"comprovante": (foto_bytes(), "pix.jpg")}, content_type="multipart/form-data")
    with app.app_context():
        m = db.session.get(Mensalidade, mid)
        assert m.status == "em_analise" and m.comprovante and m.registrado_por_id is None


def test_associado_nao_mexe_na_mensalidade_de_outro(app):
    c = logado_com_termo(app)
    with app.app_context():
        garantir_mensalidades(competencia_atual())
        maria = db.session.execute(db.select(Associado).filter_by(cpf=CPF_MARIA)).scalar_one()
        mid = db.session.execute(db.select(Mensalidade).filter_by(associado_id=maria.id)).scalars().first().id
    r = c.post(f"/associado/mensalidades/{mid}/comprovante",
               data={"comprovante": (foto_bytes(), "pix.jpg")}, content_type="multipart/form-data")
    assert r.status_code == 404


def test_equipe_gera_codigo_ve_foto_e_remove(app):
    equipe = app.test_client()
    equipe.post("/login", data={"login": "equipe", "senha": "senha-forte"})
    with app.app_context():
        aid = ana().id
    equipe.post(f"/associados/{aid}/acesso")
    with app.app_context():
        codigo = ana().codigo_acesso
    assert codigo and len(codigo) == 6
    ficha = equipe.get(f"/associados/{aid}").get_data(as_text=True)
    assert codigo in ficha and "Área do associado" in ficha

    c = app.test_client()
    primeiro_acesso(c, codigo)
    c.post("/associado/termo", data={"aceite_dados": "1", "aceite_imagem": "1"})
    c.post("/associado/foto", data={"foto": (foto_bytes(), "eu.jpg")}, content_type="multipart/form-data")
    assert equipe.get(f"/associados/{aid}/foto.jpg").status_code == 200
    equipe.post(f"/associados/{aid}/foto/remover")
    with app.app_context():
        assert ana().foto is None


def test_associado_nao_entra_no_sistema_da_equipe(app):
    c = logado_com_termo(app)
    r = c.get("/associados/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_campos_de_foto_deixam_escolher_da_galeria(app):
    """Sem o atributo capture, o celular oferece câmera OU galeria (print do Pix, foto já tirada)."""
    import pathlib
    pasta = pathlib.Path(__file__).resolve().parent.parent / "app" / "templates"
    for arquivo in pasta.rglob("*.html"):
        assert "capture=" not in arquivo.read_text(encoding="utf-8"), arquivo.name
