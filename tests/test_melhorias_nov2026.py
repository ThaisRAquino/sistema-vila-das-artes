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
