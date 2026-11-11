"""O contato oficial da associação aparece no termo, na área do associado, no recibo e nas mensagens."""
from datetime import date, timedelta

import pytest

from app import create_app, db, termo
from app.area_associado import gerar_codigo_acesso
from app.models import Associado

WHATS = "(11) 91152-1567"
EMAIL = "viladasartes.vda2022@gmail.com"


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SERVER_NAME": "localhost",
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'c.db'}"})
    app.instance_path = str(tmp_path)
    with app.app_context():
        db.create_all()
    yield app


def test_termo_tem_whatsapp_e_email():
    texto = " ".join(t for _, t in termo.SECOES)
    assert WHATS in texto and EMAIL in texto


def test_telas_de_entrada_do_associado_mostram_o_whatsapp(app):
    c = app.test_client()
    assert WHATS in c.get("/associado/entrar").get_data(as_text=True)
    assert "wa.me/5511911521567" in c.get("/associado/primeiro-acesso").get_data(as_text=True)


def test_mensagem_de_acesso_traz_o_contato(app):
    from app.regras import mensagem_whatsapp
    with app.app_context():
        a = Associado(numero_socio="0142", nome="Ana Teste", cpf="52998224725",
                      data_inscricao=date.today() - timedelta(days=30))
        a.criar_checklist()
        db.session.add(a)
        gerar_codigo_acesso(a)
        db.session.commit()
        with app.test_request_context():
            assert WHATS in mensagem_whatsapp(a, "acesso")
