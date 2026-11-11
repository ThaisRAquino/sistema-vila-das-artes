"""Testes dos perfis da equipe (presidente, administração, voluntário) e da coleta na assembleia."""
from datetime import date, timedelta

import pytest

from app import create_app, db
from app.models import Assembleia, Associado, Mensalidade, Usuario
from app.regras import competencia_atual, garantir_mensalidades


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'p.db'}"})
    app.instance_path = str(tmp_path)
    with app.app_context():
        db.create_all()
        for login, perfil in [("presidente", "presidente"), ("adm", "administracao"), ("voluntario", "voluntario")]:
            u = Usuario(nome=login.title(), login=login, perfil=perfil)
            u.definir_senha("senha-forte")
            db.session.add(u)
        a = Associado(numero_socio="0142", nome="Ana Teste", cpf="52998224725",
                      data_inscricao=date.today() - timedelta(days=100), celular="11900000000")
        a.criar_checklist()
        db.session.add(a)
        db.session.add(Assembleia(data=date.today()))
        db.session.commit()
        garantir_mensalidades(competencia_atual())
    yield app


def entrar(app, login):
    c = app.test_client()
    c.post("/login", data={"login": login, "senha": "senha-forte"})
    return c


def mensalidade_atual():
    return db.session.execute(db.select(Mensalidade).filter_by(competencia=competencia_atual())).scalar_one()


def test_voluntario_recebe_em_dinheiro_e_a_administracao_confere(app):
    vol = entrar(app, "voluntario")
    r = vol.get("/mensalidades/receber?codigo=0142")
    assert "Recebi R$ 50,00 em dinheiro" in r.get_data(as_text=True)
    with app.app_context():
        mid = mensalidade_atual().id
    vol.post(f"/mensalidades/{mid}/receber", data={"forma": "dinheiro"})
    with app.app_context():
        m = mensalidade_atual()
        assert m.status == "em_analise" and m.forma == "dinheiro" and m.comprovante is None
        assert m.registrado_por.login == "voluntario"
    assert vol.post(f"/mensalidades/{mid}/validar").status_code == 403   # voluntário não confere
    pagina = vol.get("/mensalidades/").get_data(as_text=True)
    assert "Aguardando a conferência da administração" in pagina and "Validar e gerar recibo" not in pagina
    adm = entrar(app, "adm")
    assert "confira no caixa" in adm.get("/mensalidades/").get_data(as_text=True)
    adm.post(f"/mensalidades/{mid}/validar")
    with app.app_context():
        m = mensalidade_atual()
        assert m.status == "paga" and m.numero_recibo and m.validado_por.login == "adm"


def test_nao_recebe_duas_vezes(app):
    vol = entrar(app, "voluntario")
    with app.app_context():
        mid = mensalidade_atual().id
    vol.post(f"/mensalidades/{mid}/receber", data={"forma": "dinheiro"})
    r = vol.post(f"/mensalidades/{mid}/receber", data={"forma": "dinheiro"}, follow_redirects=True)
    assert "aguardando a conferência" in r.get_data(as_text=True)


def test_comprovante_sem_arquivo_e_recusado(app):
    vol = entrar(app, "voluntario")
    with app.app_context():
        mid = mensalidade_atual().id
    r = vol.post(f"/mensalidades/{mid}/receber", data={"forma": "pix"}, follow_redirects=True)
    assert "Anexe a foto" in r.get_data(as_text=True)
    with app.app_context():
        assert mensalidade_atual().status == "aberta"


def test_voluntario_marca_presenca_mas_nao_encerra_nem_exporta(app):
    vol = entrar(app, "voluntario")
    with app.app_context():
        aid = db.session.execute(db.select(Assembleia)).scalar_one().id
        associado_id = db.session.execute(db.select(Associado)).scalar_one().id
    r = vol.post(f"/assembleias/{aid}", data={"codigo": "0142"}, headers={"X-Requested-With": "fetch"})
    assert r.get_json()["ok"] and "/mensalidades/receber?codigo=0142" in r.get_json()["receber_url"]
    for url in [f"/assembleias/{aid}/encerrar", f"/associados/{associado_id}/numero", "/acessos/gerar"]:
        assert vol.post(url).status_code == 403, url
    for url in ["/associados/exportar.xlsx", "/importar/", "/equipe/", "/associados/novo"]:
        assert vol.get(url).status_code == 403, url
    ficha = vol.get(f"/associados/{associado_id}").get_data(as_text=True)
    assert "529.982.247-25" not in ficha and "Editar ficha" not in ficha   # CPF mascarado para voluntário


def test_administracao_confere_mas_nao_mexe_na_equipe_nem_desliga(app):
    adm = entrar(app, "adm")
    with app.app_context():
        associado_id = db.session.execute(db.select(Associado)).scalar_one().id
    assert adm.get("/associados/exportar.xlsx").status_code == 200
    assert adm.get("/equipe/").status_code == 403
    assert adm.post(f"/associados/{associado_id}/desligar", data={"motivo": "Outro motivo"}).status_code == 403


def test_perfil_antigo_equipe_vira_administracao(tmp_path):
    import sqlite3
    caminho = tmp_path / "antigo.db"
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{caminho}"})
    app.instance_path = str(tmp_path)
    with app.app_context():
        u = Usuario(nome="Antiga", login="antiga", perfil="equipe")
        u.definir_senha("x")
        db.session.add(u)
        db.session.commit()
    create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{caminho}"})  # reinício do sistema
    assert sqlite3.connect(caminho).execute("select perfil from usuarios").fetchone()[0] == "administracao"


def test_presidente_baixa_backup_e_os_outros_nao(app):
    import io
    import zipfile
    r = entrar(app, "presidente").get("/equipe/backup.zip")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(r.data)).testzip() is None
    assert entrar(app, "adm").get("/equipe/backup.zip").status_code == 403


def test_foto_de_comprovante_e_reduzida_para_jpg(app):
    import io
    import os
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (4000, 3000), "white").save(buffer, "PNG")
    buffer.seek(0)
    vol = entrar(app, "voluntario")
    with app.app_context():
        mid = mensalidade_atual().id
    vol.post(f"/mensalidades/{mid}/receber", data={"forma": "pix", "comprovante": (buffer, "pix.png")},
             content_type="multipart/form-data")
    with app.app_context():
        nome = mensalidade_atual().comprovante
        assert nome.endswith(".jpg")
        with Image.open(os.path.join(app.instance_path, "comprovantes", nome)) as img:
            assert max(img.size) == 1600
