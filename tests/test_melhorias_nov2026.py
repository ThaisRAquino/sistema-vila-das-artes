"""Pedidos da associação depois da entrega do projeto (nov/2026)."""
from datetime import date

import pytest

from app import create_app, db
from app.models import Assembleia, Associado, Configuracao, Mensalidade, Presenca, Usuario
from app.regras import CHAVE_INICIO_COBRANCA, garantir_mensalidades, mensalidades_em_aberto_seguidas, situacao


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}"})
    app.instance_path = str(tmp_path)
    with app.app_context():
        db.create_all()
        for login, perfil in [("pres", "presidente"), ("adm", "administracao"), ("vol", "voluntario")]:
            u = Usuario(nome=login, login=login, perfil=perfil)
            u.definir_senha("senha-forte")
            db.session.add(u)
        a = Associado(numero_socio="0001", nome="Ana", cpf="52998224725", data_inscricao=date(2019, 1, 1))
        a.criar_checklist()
        db.session.add(a)
        db.session.commit()
    yield app


def entrar(app, login):
    c = app.test_client()
    c.post("/login", data={"login": login, "senha": "senha-forte"})
    return c


# ---------- cobrança só a partir de dezembro/2026 ----------

def test_antes_de_dezembro_a_mensalidade_fica_pendente_e_nao_conta_atraso(app):
    with app.app_context():
        Configuracao.definir(CHAVE_INICIO_COBRANCA, "2026-12")
        db.session.commit()
        for mes in ("2026-09", "2026-10", "2026-11"):
            garantir_mensalidades(mes)
        a = db.session.execute(db.select(Associado)).scalar_one()
        assert {m.status for m in a.mensalidades} == {"pendente"}
        assert mensalidades_em_aberto_seguidas(a, ate="2026-11") == 0
        garantir_mensalidades("2026-12")
        dez = next(m for m in a.mensalidades if m.competencia == "2026-12")
        assert dez.status == "aberta"
        # dezembro sem pagar conta 1; os meses de antes continuam sem contar
        assert mensalidades_em_aberto_seguidas(a, ate="2026-12") == 1


@pytest.mark.inicio_cobranca_real
def test_mensalidades_abertas_antigas_viram_pendentes_ao_atualizar(tmp_path):
    uri = f"sqlite:///{tmp_path / 'velho.db'}"
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": uri})
    with app.app_context():
        db.create_all()
        a = Associado(numero_socio="0001", nome="Ana", cpf="52998224725", data_inscricao=date(2019, 1, 1))
        db.session.add(a)
        db.session.flush()
        db.session.add_all([Mensalidade(associado=a, competencia="2026-11", valor=50, status="aberta"),
                            Mensalidade(associado=a, competencia="2026-10", valor=50, status="paga"),
                            Mensalidade(associado=a, competencia="2026-12", valor=50, status="aberta")])
        db.session.commit()
    app2 = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": uri})  # como no "Reload" do site
    with app2.app_context():
        st = {m.competencia: m.status for m in db.session.execute(db.select(Mensalidade)).scalars()}
        assert st == {"2026-11": "pendente", "2026-10": "paga", "2026-12": "aberta"}


def test_pendente_pode_ser_paga_e_aparece_com_aviso(app):
    with app.app_context():
        Configuracao.definir(CHAVE_INICIO_COBRANCA, "2099-01")
        db.session.commit()
    c = entrar(app, "pres")
    pagina = c.get("/mensalidades/").get_data(as_text=True)
    assert "A cobrança começa em janeiro de 2099" in pagina and "Pendente" in pagina
    assert "Cobrar no WhatsApp" not in pagina  # não cobra antes da cobrança começar
    with app.app_context():
        m = db.session.execute(db.select(Mensalidade)).scalar_one()
        assert m.status == "pendente"
        mid = m.id
    c.post(f"/mensalidades/{mid}/receber", data={"forma": "dinheiro"})
    with app.app_context():
        assert db.session.get(Mensalidade, mid).status == "em_analise"
    c.post(f"/mensalidades/{mid}/recusar", data={"motivo": "Valor diferente"})
    with app.app_context():
        assert db.session.get(Mensalidade, mid).status == "pendente"  # recusa antes da cobrança não vira atraso
        a = db.session.execute(db.select(Associado)).scalar_one()
        assert situacao(a)["atrasadas"] == 0


# ---------- excluir lista de presença ----------

def criar_assembleia(app):
    with app.app_context():
        asm = Assembleia(data=date(2026, 11, 8))
        db.session.add(asm)
        db.session.flush()
        db.session.add(Presenca(assembleia_id=asm.id, associado_id=1))
        db.session.commit()
        return asm.id


def test_excluir_lista_de_presenca_apaga_tudo(app):
    aid = criar_assembleia(app)
    c = entrar(app, "adm")
    assert "Excluir esta lista de presença" in c.get(f"/assembleias/{aid}").get_data(as_text=True)
    c.post(f"/assembleias/{aid}/excluir", data={})  # sem confirmar: não apaga
    with app.app_context():
        assert db.session.get(Assembleia, aid)
    r = c.post(f"/assembleias/{aid}/excluir", data={"confirmar": "1"}, follow_redirects=True)
    assert "excluída (1 presença(s) apagada(s))" in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Assembleia, aid) is None
        assert db.session.execute(db.select(db.func.count()).select_from(Presenca)).scalar() == 0


def test_voluntario_nao_exclui_lista(app):
    aid = criar_assembleia(app)
    c = entrar(app, "vol")
    assert "Excluir esta lista de presença" not in c.get(f"/assembleias/{aid}").get_data(as_text=True)
    assert c.post(f"/assembleias/{aid}/excluir", data={"confirmar": "1"}).status_code == 403
    with app.app_context():
        assert db.session.get(Assembleia, aid)


# ---------- documentos enviados pelo associado e pela equipe (28/11) ----------

def foto():
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (900, 600), (200, 200, 200)).save(b, "JPEG")
    b.seek(0)
    return b


def associado_logado(app):
    from datetime import datetime
    from app import termo
    with app.app_context():
        a = db.session.execute(db.select(Associado).filter_by(cpf="52998224725")).scalar_one()
        a.definir_senha("minhasenha")
        a.termo_aceito_em, a.termo_versao = datetime.now(), termo.VERSAO
        db.session.commit()
    c = app.test_client()
    c.post("/associado/entrar", data={"cpf": "52998224725", "senha": "minhasenha"})
    return c


def doc(app, tipo="RG"):
    from app.models import Documento
    with app.app_context():
        return db.session.execute(db.select(Documento).filter_by(tipo=tipo)).scalar_one()


def test_associado_envia_documento_e_administracao_aprova(app):
    import os
    c = associado_logado(app)
    assert "Meus documentos" in c.get("/associado/").get_data(as_text=True)
    d = doc(app)
    c.post(f"/associado/documentos/{d.id}", data={"arquivo": (foto(), "rg.jpg")}, content_type="multipart/form-data")
    d = doc(app)
    assert d.status == "em_analise" and d.arquivo and d.enviado_pelo_associado
    assert os.path.exists(os.path.join(app.instance_path, "documentos", d.arquivo))
    adm = entrar(app, "adm")
    assert "Documentos enviados para conferir (1)" in adm.get("/").get_data(as_text=True)
    assert adm.get(f"/associados/1/documentos/{d.id}/arquivo").status_code == 200
    adm.post(f"/associados/1/documentos/{d.id}/conferir", data={"acao": "aprovar"})
    assert doc(app).status == "entregue"


def test_documento_recusado_volta_a_faltar_com_motivo(app):
    c = associado_logado(app)
    d = doc(app, "CPF")
    c.post(f"/associado/documentos/{d.id}", data={"arquivo": (foto(), "cpf.jpg")}, content_type="multipart/form-data")
    entrar(app, "adm").post(f"/associados/1/documentos/{d.id}/conferir", data={"acao": "recusar", "motivo": "Documento ilegível ou cortado"})
    d = doc(app, "CPF")
    assert d.status == "pendente" and d.arquivo is None and d.motivo_recusa == "Documento ilegível ou cortado"
    assert "Recusado: Documento ilegível ou cortado" in c.get("/associado/").get_data(as_text=True)


def test_equipe_anexa_documento(app):
    vol = entrar(app, "vol")
    d = doc(app, "Comprovante de endereço")
    vol.post(f"/associados/1/documentos/{d.id}/enviar", data={"arquivo": (foto(), "conta.jpg")}, content_type="multipart/form-data")
    assert doc(app, "Comprovante de endereço").status == "em_analise"   # voluntário: a administração confere
    assert vol.get(f"/associados/1/documentos/{d.id}/arquivo").status_code == 403  # voluntário não abre o documento
    d2 = doc(app, "Título de eleitor")
    entrar(app, "adm").post(f"/associados/1/documentos/{d2.id}/enviar", data={"arquivo": (foto(), "t.jpg")}, content_type="multipart/form-data")
    assert doc(app, "Título de eleitor").status == "entregue"  # administração: já fica entregue


def test_associado_nao_envia_documento_de_outro(app):
    from app.models import Documento
    with app.app_context():
        b = Associado(numero_socio="0002", nome="Bia", cpf="39053344705", data_inscricao=date(2019, 1, 1))
        b.criar_checklist()
        db.session.add(b)
        db.session.commit()
        outro = db.session.execute(db.select(Documento).filter_by(associado_id=b.id, tipo="RG")).scalar_one().id
    c = associado_logado(app)
    r = c.post(f"/associado/documentos/{outro}", data={"arquivo": (foto(), "x.jpg")}, content_type="multipart/form-data")
    assert r.status_code == 404
