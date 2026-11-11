"""Testes do modo de produção, páginas de erro, app instalável e backup."""
import os
import sqlite3
import zipfile


import backup
from app import create_app, db
from app.models import Associado


def criar(tmp_path, **config):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'p.db'}", **config})
    app.instance_path = str(tmp_path)
    return app


def test_modo_producao_usa_https_e_cookie_seguro(tmp_path, monkeypatch):
    monkeypatch.setenv("VDA_PRODUCAO", "1")
    app = criar(tmp_path)
    assert app.config["SESSION_COOKIE_SECURE"]
    c = app.test_client()
    r = c.get("/associado/entrar", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "viladasartes.org"})
    assert r.headers["Strict-Transport-Security"]
    # atrás do proxy da hospedagem, o link do WhatsApp com o código de acesso sai com https e o domínio certo
    from urllib.parse import unquote
    from app.area_associado import gerar_codigo_acesso
    from app.models import Usuario
    with app.app_context():
        u = Usuario(nome="Equipe", login="equipe")
        u.definir_senha("senha-forte")
        a = Associado(numero_socio="0142", nome="Ana Teste", cpf="52998224725", celular="11900000142")
        gerar_codigo_acesso(a)
        db.session.add_all([u, a])
        db.session.commit()
        aid = a.id
    proxy = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "viladasartes.org"}
    c.post("/login", data={"login": "equipe", "senha": "senha-forte"}, headers=proxy)
    r = c.post(f"/avisos/{aid}/whatsapp", data={"motivo": "acesso"}, headers=proxy)
    assert "https://viladasartes.org/associado/primeiro-acesso" in unquote(r.headers["Location"])


def test_cabecalhos_de_seguranca_e_pagina_de_erro(tmp_path):
    c = criar(tmp_path).test_client()
    r = c.get("/nao-existe")
    assert r.status_code == 404 and "Página não encontrada" in r.get_data(as_text=True)
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"


def test_app_instalavel(tmp_path):
    c = criar(tmp_path).test_client()
    sw = c.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["Content-Type"] and sw.headers["Cache-Control"] == "no-cache"
    manifesto = c.get("/static/manifest-associado.webmanifest").get_json(force=True)
    assert manifesto["start_url"] == "/associado/" and any(i.get("purpose") == "maskable" for i in manifesto["icons"])
    pagina = c.get("/associado/entrar").get_data(as_text=True)
    assert "manifest-associado.webmanifest" in pagina and 'data-limpar-carteirinha="1"' in pagina


def test_backup_tem_banco_fotos_e_comprovantes(tmp_path, monkeypatch):
    instance = tmp_path / "instance"
    (instance / "fotos").mkdir(parents=True)
    (instance / "comprovantes").mkdir()
    (instance / "fotos" / "a.jpg").write_bytes(b"foto")
    (instance / "comprovantes" / "b.pdf").write_bytes(b"pdf")
    con = sqlite3.connect(instance / "vila_das_artes.db")
    con.execute("create table t (x)")
    con.execute("insert into t values (42)")
    con.commit()
    con.close()
    monkeypatch.setattr(backup, "INSTANCE", str(instance))
    monkeypatch.setattr(backup, "BASE", str(tmp_path))
    monkeypatch.setattr(backup, "PASTA_BACKUP", str(tmp_path / "backups"))
    destino = backup.fazer_backup()
    with zipfile.ZipFile(destino) as z:
        nomes = set(z.namelist())
        assert {"instance/vila_das_artes.db", "instance/fotos/a.jpg", "instance/comprovantes/b.pdf"} <= nomes
        z.extract("instance/vila_das_artes.db", tmp_path / "restaurado")
    restaurado = sqlite3.connect(tmp_path / "restaurado" / "instance" / "vila_das_artes.db")
    assert restaurado.execute("select x from t").fetchone()[0] == 42


def test_backup_guarda_so_os_mais_recentes(tmp_path, monkeypatch):
    pasta = tmp_path / "backups"
    pasta.mkdir()
    for dia in range(1, 6):
        (pasta / f"vila-das-artes-2026-01-0{dia}-0000.zip").write_bytes(b"x")
    monkeypatch.setattr(backup, "INSTANCE", str(tmp_path / "vazio"))
    monkeypatch.setattr(backup, "PASTA_BACKUP", str(pasta))
    backup.fazer_backup(manter=3)
    assert len(os.listdir(pasta)) == 3
