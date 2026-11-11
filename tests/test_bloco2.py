"""Testes do 2º bloco: mensalidades com validação, cobrança dos mutirantes, assembleias, alertas e avisos."""
import io
from datetime import date, timedelta

import pytest

from app import create_app, db
from app.models import Assembleia, Associado, Aviso, Mensalidade, Presenca, Usuario
from app.regras import (
    competencia_anterior,
    competencia_atual,
    faltas_seguidas,
    garantir_mensalidades,
    mensalidades_em_aberto_seguidas,
    proxima_assembleia,
    segundo_domingo,
    situacao,
)

def _png():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), "white").save(buffer, "PNG")
    return buffer.getvalue()


PNG = _png()  # imagem de verdade: o sistema abre e reduz as fotos de comprovante


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'b2.db'}",
    })
    app.instance_path = str(tmp_path)  # comprovantes de teste ficam na pasta temporária
    with app.app_context():
        db.create_all()
        u = Usuario(nome="Equipe Teste", login="equipe")
        u.definir_senha("senha-forte")
        db.session.add(u)
        inicio = date.today() - timedelta(days=400)
        for numero, nome, cpf, categoria, cel in [
            ("0142", "Ana Teste", "52998224725", "regular", "11999990000"),
            ("0057", "Maria Mutirante", "39053344705", "mutirante", "11988880000"),
        ]:
            a = Associado(numero_socio=numero, nome=nome, cpf=cpf, categoria=categoria,
                          data_inscricao=inicio, celular=cel)
            a.criar_checklist()
            db.session.add(a)
        db.session.commit()
    yield app


@pytest.fixture
def cliente(app):
    c = app.test_client()
    c.post("/login", data={"login": "equipe", "senha": "senha-forte"})
    return c


def associado(numero):
    return db.session.execute(db.select(Associado).filter_by(numero_socio=numero)).scalar_one()


def mensalidade(numero, competencia):
    a = associado(numero)
    return db.session.execute(db.select(Mensalidade).filter_by(associado_id=a.id, competencia=competencia)).scalar_one()


# ---------- datas ----------

def test_segundo_domingo_e_proxima_assembleia():
    assert segundo_domingo(2026, 10) == date(2026, 10, 11)
    assert segundo_domingo(2026, 11) == date(2026, 11, 8)
    assert proxima_assembleia(date(2026, 10, 16)) == date(2026, 11, 8)
    assert proxima_assembleia(date(2026, 10, 11)) == date(2026, 10, 11)


def test_competencia_anterior():
    assert competencia_anterior("2026-01") == "2025-12"
    assert competencia_anterior("2026-10", 3) == "2026-07"


# ---------- mensalidades ----------

def test_mes_gera_mensalidades_e_mutirante_isento(app, cliente):
    cliente.get("/mensalidades/")
    with app.app_context():
        mes = competencia_atual()
        assert mensalidade("0142", mes).status == "aberta"
        assert mensalidade("0057", mes).status == "isenta"


def test_fluxo_comprovante_validacao_e_recibo(app, cliente):
    cliente.get("/mensalidades/")
    with app.app_context():
        m_id = mensalidade("0142", competencia_atual()).id

    # sem arquivo: não aceita
    r = cliente.post(f"/mensalidades/{m_id}/comprovante", data={"forma": "pix"}, follow_redirects=True)
    assert "Anexe a foto" in r.get_data(as_text=True)

    # formato proibido
    r = cliente.post(f"/mensalidades/{m_id}/comprovante",
                     data={"forma": "pix", "comprovante": (io.BytesIO(b"x"), "virus.exe")},
                     content_type="multipart/form-data", follow_redirects=True)
    assert "Formato não aceito" in r.get_data(as_text=True)

    # comprovante ok -> em análise (ainda NÃO está paga)
    cliente.post(f"/mensalidades/{m_id}/comprovante",
                 data={"forma": "pix", "comprovante": (io.BytesIO(PNG), "pix.png")},
                 content_type="multipart/form-data")
    with app.app_context():
        m = db.session.get(Mensalidade, m_id)
        assert m.status == "em_analise" and m.comprovante.endswith(".jpg") and m.numero_recibo is None

    # a equipe valida -> paga + recibo
    cliente.post(f"/mensalidades/{m_id}/validar")
    with app.app_context():
        m = db.session.get(Mensalidade, m_id)
        assert m.status == "paga" and m.validado_por.login == "equipe"
        assert m.numero_recibo == f"{m.competencia[:4]}-00001"
    recibo = cliente.get(f"/mensalidades/{m_id}/recibo").get_data(as_text=True)
    assert "Recibo nº" in recibo and "Ana Teste" in recibo


def test_nao_valida_sem_comprovante(app, cliente):
    cliente.get("/mensalidades/")
    with app.app_context():
        m_id = mensalidade("0142", competencia_atual()).id
    cliente.post(f"/mensalidades/{m_id}/validar")
    with app.app_context():
        assert db.session.get(Mensalidade, m_id).status == "aberta"


def test_recusar_comprovante_exige_motivo(app, cliente):
    cliente.get("/mensalidades/")
    with app.app_context():
        m_id = mensalidade("0142", competencia_atual()).id
    cliente.post(f"/mensalidades/{m_id}/comprovante",
                 data={"comprovante": (io.BytesIO(PNG), "c.png")}, content_type="multipart/form-data")
    cliente.post(f"/mensalidades/{m_id}/recusar", data={"motivo": ""})
    with app.app_context():
        assert db.session.get(Mensalidade, m_id).status == "em_analise"
    cliente.post(f"/mensalidades/{m_id}/recusar", data={"motivo": "Comprovante ilegível"})
    with app.app_context():
        m = db.session.get(Mensalidade, m_id)
        assert m.status == "recusada" and m.motivo_recusa == "Comprovante ilegível"


def test_ativar_cobranca_dos_mutirantes(app, cliente):
    cliente.get("/mensalidades/")
    mes = None
    with app.app_context():
        mes = competencia_atual()
        assert mensalidade("0057", mes).status == "isenta"
    cliente.post("/mensalidades/cobranca-mutirantes", data={"acao": "ativar", "desde": mes})
    with app.app_context():
        assert mensalidade("0057", mes).status == "aberta"


# ---------- alertas ----------

def test_tres_mensalidades_em_aberto_viram_risco(app):
    with app.app_context():
        atual = competencia_atual()
        for i in range(1, 4):
            garantir_mensalidades(competencia_anterior(atual, i))
        a = associado("0142")
        assert mensalidades_em_aberto_seguidas(a) == 3
        assert situacao(a)["nivel"] == "risco"
        # mutirante isento não entra em risco por mensalidade
        assert situacao(associado("0057"))["atrasadas"] == 0


def test_em_analise_nao_conta_como_atraso(app):
    with app.app_context():
        atual = competencia_atual()
        for i in range(1, 4):
            garantir_mensalidades(competencia_anterior(atual, i))
        mensalidade("0142", competencia_anterior(atual, 1)).status = "em_analise"
        db.session.commit()
        assert mensalidades_em_aberto_seguidas(associado("0142")) == 0


# ---------- assembleias ----------

def criar_assembleias(n, encerradas=True):
    ids = []
    hoje = date.today()
    for i in range(n, 0, -1):
        a = Assembleia(data=hoje - timedelta(days=30 * i), encerrada=encerradas)
        db.session.add(a)
        db.session.flush()
        ids.append(a.id)
    db.session.commit()
    return ids


def test_presenca_por_numero_e_por_qr(app, cliente):
    with app.app_context():
        asm = Assembleia(data=date.today())
        db.session.add(asm)
        db.session.commit()
        asm_id = asm.id
        qr = associado("0057").qr_codigo

    r = cliente.post(f"/assembleias/{asm_id}", data={"codigo": "142"}, headers={"X-Requested-With": "fetch"})
    assert r.get_json()["ok"] is True
    r = cliente.post(f"/assembleias/{asm_id}", data={"codigo": "142"}, headers={"X-Requested-With": "fetch"})
    assert r.get_json()["ok"] is False and "já estava presente" in r.get_json()["mensagem"]
    r = cliente.post(f"/assembleias/{asm_id}", data={"codigo": qr.lower()}, headers={"X-Requested-With": "fetch"})
    assert r.get_json()["ok"] is True
    r = cliente.post(f"/assembleias/{asm_id}", data={"codigo": "9999"}, headers={"X-Requested-With": "fetch"})
    assert r.get_json()["ok"] is False
    with app.app_context():
        formas = sorted(p.forma for p in db.session.execute(db.select(Presenca)).scalars())
        assert formas == ["numero", "qr"]


def test_nao_marca_presenca_com_lista_encerrada(app, cliente):
    with app.app_context():
        asm = Assembleia(data=date.today(), encerrada=True)
        db.session.add(asm)
        db.session.commit()
        asm_id = asm.id
    r = cliente.post(f"/assembleias/{asm_id}", data={"codigo": "142"}, headers={"X-Requested-With": "fetch"})
    assert r.get_json()["ok"] is False


def test_tres_faltas_seguidas_viram_risco(app):
    with app.app_context():
        ids = criar_assembleias(4)
        ana = associado("0142")
        # presente só na mais antiga -> 3 faltas seguidas
        db.session.add(Presenca(assembleia_id=ids[0], associado_id=ana.id))
        db.session.commit()
        assert faltas_seguidas(ana) == 3
        assert situacao(ana)["nivel"] == "risco"
        # presente na mais recente -> zera
        db.session.add(Presenca(assembleia_id=ids[-1], associado_id=ana.id))
        db.session.commit()
        assert faltas_seguidas(ana) == 0


def test_lista_aberta_nao_conta_falta(app):
    with app.app_context():
        criar_assembleias(2)
        db.session.add(Assembleia(data=date.today(), encerrada=False))
        db.session.commit()
        assert faltas_seguidas(associado("0142")) == 2
        assert situacao(associado("0142"))["nivel"] == "atencao"


# ---------- avisos ----------

def test_aviso_whatsapp_registra_e_abre_link(app, cliente):
    with app.app_context():
        a_id = associado("0142").id
    r = cliente.post(f"/avisos/{a_id}/whatsapp", data={"motivo": "assembleia"})
    assert r.status_code == 302 and r.headers["Location"].startswith("https://wa.me/5511999990000?text=")
    with app.app_context():
        aviso = db.session.execute(db.select(Aviso)).scalar_one()
        assert aviso.motivo == "assembleia" and "Vila das Artes" in aviso.mensagem


def test_paginas_do_bloco2_abrem(app, cliente):
    with app.app_context():
        a_id = associado("0142").id
        criar_assembleias(2)
    for url in ["/", "/mensalidades/", "/assembleias/", "/avisos/", f"/associados/{a_id}", "/associados/"]:
        assert cliente.get(url).status_code == 200, url
