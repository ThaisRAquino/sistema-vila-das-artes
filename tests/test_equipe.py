"""Testes dos usuários da equipe, troca de senha, bloqueio de tentativas e atualização do banco."""
import re
import sqlite3

import pytest

from app import create_app, db
from app.models import TentativaAcesso, Usuario


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'eq.db'}",
    })
    app.instance_path = str(tmp_path)
    with app.app_context():
        db.create_all()
        p = Usuario(nome="Presidente", login="presidente", perfil="presidente")
        p.definir_senha("senha-forte")
        e = Usuario(nome="Equipe Um", login="equipe1", perfil="equipe")
        e.definir_senha("senha-forte")
        db.session.add_all([p, e])
        db.session.commit()
    yield app


def entrar(app, login, senha="senha-forte"):
    c = app.test_client()
    r = c.post("/login", data={"login": login, "senha": senha})
    return c, r


def usuario(login):
    return db.session.execute(db.select(Usuario).filter_by(login=login)).scalar_one()


def test_so_presidente_ve_a_tela_equipe(app):
    c, _ = entrar(app, "equipe1")
    assert c.get("/equipe/").status_code == 403
    assert "Equipe</a>" not in c.get("/").get_data(as_text=True)
    c, _ = entrar(app, "presidente")
    assert c.get("/equipe/").status_code == 200


def test_presidente_cadastra_e_pessoa_troca_a_senha_provisoria(app):
    c, _ = entrar(app, "presidente")
    r = c.post("/equipe/novo", data={"nome": "Maria Silva", "login": "Maria.Silva", "perfil": "equipe"}, follow_redirects=True)
    senha = re.search(r"Senha provisória: (\w+)", r.get_data(as_text=True)).group(1)
    nova, r = entrar(app, "maria.silva", senha)
    assert r.headers["Location"].endswith("/equipe/minha-senha")
    assert "/equipe/minha-senha" in nova.get("/associados/").headers["Location"]  # bloqueado até trocar
    nova.post("/equipe/minha-senha", data={"atual": senha, "nova": "minha-senha-1", "confirmar": "minha-senha-1"})
    assert nova.get("/associados/").status_code == 200
    with app.app_context():
        u = usuario("maria.silva")
        assert u.conferir_senha("minha-senha-1") and not u.trocar_senha


def test_nao_aceita_usuario_repetido(app):
    c, _ = entrar(app, "presidente")
    r = c.post("/equipe/novo", data={"nome": "Outro", "login": "equipe1", "perfil": "equipe"}, follow_redirects=True)
    assert "Já existe" in r.get_data(as_text=True)


def test_desativar_impede_entrada(app):
    c, _ = entrar(app, "presidente")
    with app.app_context():
        uid = usuario("equipe1").id
    c.post(f"/equipe/{uid}/ativo")
    _, r = entrar(app, "equipe1")
    assert "incorretos" in r.get_data(as_text=True)


def test_sempre_fica_um_presidente(app):
    c, _ = entrar(app, "presidente")
    with app.app_context():
        pid = usuario("presidente").id
    r = c.post(f"/equipe/{pid}/perfil", data={"perfil": "equipe"}, follow_redirects=True)
    assert "pelo menos um presidente" in r.get_data(as_text=True)
    r = c.post(f"/equipe/{pid}/ativo", follow_redirects=True)
    assert "próprio acesso" in r.get_data(as_text=True)


def test_bloqueio_do_login_da_equipe_vale_mesmo_trocando_de_navegador(app):
    for _ in range(5):
        entrar(app, "equipe1", "errada")          # cada chamada é um "navegador" novo
    _, r = entrar(app, "equipe1")                  # senha certa, mas bloqueado
    assert "Muitas tentativas" in r.get_data(as_text=True)
    c, _ = entrar(app, "presidente")
    with app.app_context():
        uid = usuario("equipe1").id
    r = c.post(f"/equipe/{uid}/senha", follow_redirects=True)   # presidente desbloqueia com senha nova
    senha = re.search(r"provisória de Equipe Um: (\w+)", r.get_data(as_text=True)).group(1)
    _, r = entrar(app, "equipe1", senha)
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(TentativaAcesso, "equipe:equipe1") is None


def test_banco_antigo_ganha_colunas_novas_sem_perder_dados(tmp_path):
    caminho = tmp_path / "antigo.db"
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nome VARCHAR(120) NOT NULL, login VARCHAR(60) NOT NULL UNIQUE,"
                " senha_hash VARCHAR(255) NOT NULL, perfil VARCHAR(20) NOT NULL, ativo BOOLEAN NOT NULL,"
                " criado_em DATETIME NOT NULL, atualizado_em DATETIME NOT NULL)")
    con.execute("INSERT INTO usuarios VALUES (1, 'Admin', 'admin', 'x', 'presidente', 1, '2026-01-01', '2026-01-01')")
    con.commit()
    con.close()
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{caminho}"})
    app.instance_path = str(tmp_path)
    with app.app_context():
        u = db.session.get(Usuario, 1)
        assert u.login == "admin" and not u.trocar_senha
