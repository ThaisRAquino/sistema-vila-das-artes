"""Testes do 1º bloco: login, cadastro, nº de sócio único e editável, documentos e QR.

Rodar:  python -m pytest
"""
import pytest

from app import create_app, db
from app.models import Associado, HistoricoNumeroSocio, Usuario
from app.utils import cpf_valido

CPF_1 = "52998224725"
CPF_2 = "11144477735"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'teste.db'}",
    })
    with app.app_context():
        db.create_all()
        u = Usuario(nome="Equipe Teste", login="equipe")
        u.definir_senha("senha-forte")
        db.session.add(u)
        db.session.commit()
    yield app


@pytest.fixture
def cliente(app):
    c = app.test_client()
    c.post("/login", data={"login": "equipe", "senha": "senha-forte"})
    return c


def cadastrar(cliente, numero="0001", cpf=CPF_1, nome="Ana Teste", **extra):
    dados = {"numero_socio": numero, "nome": nome, "cpf": cpf, "categoria": "regular", "consentimento": "1"}
    dados.update(extra)
    return cliente.post("/associados/novo", data=dados, follow_redirects=True)


def test_cpf_valido():
    assert cpf_valido("529.982.247-25")
    assert not cpf_valido("111.111.111-11")
    assert not cpf_valido("123")


def test_paginas_exigem_login(app):
    resposta = app.test_client().get("/associados/")
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


def test_login_errado(app):
    resposta = app.test_client().post("/login", data={"login": "equipe", "senha": "x"})
    assert "Usuário ou senha incorretos" in resposta.get_data(as_text=True)


def test_cadastro_cria_checklist_e_qr(app, cliente):
    resposta = cadastrar(cliente)
    assert "nº de sócio 0001" in resposta.get_data(as_text=True)
    with app.app_context():
        a = db.session.execute(db.select(Associado)).scalar_one()
        assert a.docs_total == 5 and a.docs_entregues == 0
        assert a.qr_codigo.startswith("VDA-")
        assert a.consentimento_lgpd_em is not None


def test_numero_repetido_e_bloqueado(app, cliente):
    cadastrar(cliente, numero="0010")
    resposta = cadastrar(cliente, numero="10", cpf=CPF_2, nome="Outro")
    assert "já está em uso" in resposta.get_data(as_text=True)
    with app.app_context():
        assert db.session.execute(db.select(db.func.count()).select_from(Associado)).scalar() == 1


def test_cpf_repetido_e_bloqueado(app, cliente):
    cadastrar(cliente, numero="0001")
    resposta = cadastrar(cliente, numero="0002", nome="Duplicado")
    assert "já está cadastrado" in resposta.get_data(as_text=True)


def test_sem_consentimento_lgpd_nao_cadastra(app, cliente):
    resposta = cliente.post("/associados/novo", data={"numero_socio": "0001", "nome": "X", "cpf": CPF_1}, follow_redirects=True)
    assert "LGPD" in resposta.get_data(as_text=True)


def test_alterar_numero_registra_historico(app, cliente):
    cadastrar(cliente, numero="0001")
    cadastrar(cliente, numero="0002", cpf=CPF_2, nome="Bia")
    with app.app_context():
        a_id = db.session.execute(db.select(Associado.id).filter_by(numero_socio="0001")).scalar()

    # número de outra pessoa: bloqueado
    r = cliente.post(f"/associados/{a_id}/numero", data={"numero_socio": "2"}, follow_redirects=True)
    assert "já pertence a outro associado" in r.get_data(as_text=True)

    # número livre: alterado e registrado
    cliente.post(f"/associados/{a_id}/numero", data={"numero_socio": "142", "motivo": "corrigir"}, follow_redirects=True)
    with app.app_context():
        a = db.session.get(Associado, a_id)
        assert a.numero_socio == "0142"
        h = db.session.execute(db.select(HistoricoNumeroSocio)).scalar_one()
        assert (h.numero_anterior, h.numero_novo, h.alterado_por.login) == ("0001", "0142", "equipe")


def test_marcar_documento_entregue(app, cliente):
    cadastrar(cliente)
    with app.app_context():
        a = db.session.execute(db.select(Associado)).scalar_one()
        a_id, d_id = a.id, a.documentos[0].id
    cliente.post(f"/associados/{a_id}/documentos/{d_id}")
    with app.app_context():
        d = db.session.get(Associado, a_id).documentos[0]
        assert d.status == "entregue" and d.conferido_por.login == "equipe"


def test_qr_e_renovacao(app, cliente):
    cadastrar(cliente)
    with app.app_context():
        a = db.session.execute(db.select(Associado)).scalar_one()
        a_id, codigo = a.id, a.qr_codigo
    resposta = cliente.get(f"/associados/{a_id}/qr.png")
    assert resposta.mimetype == "image/png" and resposta.data[:4] == b"\x89PNG"
    cliente.post(f"/associados/{a_id}/qr/renovar")
    with app.app_context():
        assert db.session.get(Associado, a_id).qr_codigo != codigo


def test_busca_por_numero_e_filtro_mutirante(app, cliente):
    cadastrar(cliente, numero="0142")
    cadastrar(cliente, numero="0057", cpf=CPF_2, nome="Maria Mutirante", categoria="mutirante")
    texto = cliente.get("/associados/?q=142").get_data(as_text=True)
    assert "Ana Teste" in texto and "Maria Mutirante" not in texto
    texto = cliente.get("/associados/?filtro=mutirante").get_data(as_text=True)
    assert "Maria Mutirante" in texto and "Ana Teste" not in texto


def test_csrf_bloqueia_post_sem_token(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'csrf.db'}"})
    resposta = app.test_client().post("/login", data={"login": "x", "senha": "y"})
    assert resposta.status_code == 400
