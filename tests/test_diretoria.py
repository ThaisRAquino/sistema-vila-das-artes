"""Testes da exportação da lista, do desligamento registrado pela diretoria e dos indicadores."""
import io
from datetime import date, timedelta

import pytest
from openpyxl import load_workbook

from app import create_app, db
from app.models import Assembleia, Associado, Mensalidade, RegistroExportacao, Usuario
from app.regras import competencia_atual, faltas_seguidas, garantir_mensalidades


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'd.db'}"})
    app.instance_path = str(tmp_path)
    with app.app_context():
        db.create_all()
        for login, perfil in [("presidente", "presidente"), ("equipe", "equipe")]:
            u = Usuario(nome=login.title(), login=login, perfil=perfil)
            u.definir_senha("senha-forte")
            db.session.add(u)
        inicio = date.today() - timedelta(days=200)
        for numero, nome, cpf, completos in [("0142", "Ana Teste", "52998224725", True), ("0231", "José Teste", "11144477735", False)]:
            a = Associado(numero_socio=numero, nome=nome, cpf=cpf, data_inscricao=inicio, celular="11900000000")
            a.criar_checklist()
            if completos:
                for d in a.documentos:
                    d.status = "entregue"
            db.session.add(a)
        db.session.commit()
    yield app


def entrar(app, login):
    c = app.test_client()
    c.post("/login", data={"login": login, "senha": "senha-forte"})
    return c


def associado(numero):
    return db.session.execute(db.select(Associado).filter_by(numero_socio=numero)).scalar_one()


def test_exporta_excel_com_os_filtros_da_tela_e_registra(app):
    c = entrar(app, "equipe")
    r = c.get("/associados/exportar.xlsx?filtro=completos")
    assert r.status_code == 200
    aba = load_workbook(io.BytesIO(r.data)).active
    linhas = list(aba.iter_rows(values_only=True))
    assert linhas[0][:3] == ("Nº de sócio", "Nome completo", "CPF")
    assert len(linhas) == 2 and linhas[1][1] == "Ana Teste" and linhas[1][2] == "529.982.247-25"
    todos = load_workbook(io.BytesIO(c.get("/associados/exportar.xlsx").data)).active
    assert todos.max_row == 3
    with app.app_context():
        registros = db.session.execute(db.select(RegistroExportacao)).scalars().all()
        assert [r.quantidade for r in registros] == [1, 2] and registros[0].usuario.login == "equipe"


def test_so_presidente_registra_desligamento(app):
    with app.app_context():
        aid = associado("0231").id
    r = entrar(app, "equipe").post(f"/associados/{aid}/desligar", data={"motivo": "3 mensalidades seguidas em aberto"})
    assert r.status_code == 403
    with app.app_context():
        assert associado("0231").situacao == "ativo"


def test_desligamento_tira_das_listas_mensalidades_e_area(app):
    with app.app_context():
        a = associado("0231")
        a.definir_senha("senha123")
        db.session.commit()
        aid = a.id
    c = entrar(app, "presidente")
    c.post(f"/associados/{aid}/desligar", data={"motivo": "3 mensalidades seguidas em aberto",
                                               "data_decisao": date.today().isoformat(), "observacao": "reunião"})
    with app.app_context():
        a = associado("0231")
        assert a.situacao == "desligado" and a.historico_situacao[0].registrado_por.login == "presidente"
        garantir_mensalidades(competencia_atual())
        assert not db.session.execute(db.select(Mensalidade).filter_by(associado_id=aid, competencia=competencia_atual())).first()
    c.get("/associados/")  # consome a mensagem de confirmação
    assert "José Teste" not in c.get("/associados/").get_data(as_text=True)
    assert "José Teste" in c.get("/associados/?filtro=desligados").get_data(as_text=True)
    r = app.test_client().post("/associado/entrar", data={"cpf": "11144477735", "senha": "senha123"})
    assert "incorretos" in r.get_data(as_text=True)  # desligado não entra na área do associado


def test_motivo_e_obrigatorio(app):
    with app.app_context():
        aid = associado("0231").id
    entrar(app, "presidente").post(f"/associados/{aid}/desligar", data={"motivo": ""})
    with app.app_context():
        assert associado("0231").situacao == "ativo"


def test_reativado_comeca_a_contar_faltas_do_zero(app):
    with app.app_context():
        for dias in (90, 60, 30):
            db.session.add(Assembleia(data=date.today() - timedelta(days=dias), encerrada=True))
        db.session.commit()
        assert faltas_seguidas(associado("0231")) == 3
        aid = associado("0231").id
    c = entrar(app, "presidente")
    c.post(f"/associados/{aid}/desligar", data={"motivo": "3 faltas seguidas nas assembleias"})
    c.post(f"/associados/{aid}/reativar")
    with app.app_context():
        a = associado("0231")
        assert a.situacao == "ativo" and faltas_seguidas(a) == 0
        assert [h.situacao for h in a.historico_situacao] == ["ativo", "desligado"]


def test_indicadores_mostram_antes_e_depois(app):
    pagina = entrar(app, "equipe").get("/indicadores/").get_data(as_text=True)
    assert "508 fichas em papel" in pagina and "4 casos de nº de sócio repetido" in pagina
    assert "<b>50%</b> (1 de 2)" in pagina  # documentação completa calculada pelo sistema
