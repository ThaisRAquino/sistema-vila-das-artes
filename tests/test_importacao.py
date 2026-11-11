"""Testes da importação por planilha e dos códigos de acesso em lote."""
import io
import os
import re
from datetime import date, datetime, timedelta

import pytest
from openpyxl import Workbook, load_workbook

from app import create_app, db
from app.models import Associado, Usuario

CPF_EXISTENTE = "52998224725"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'imp.db'}",
    })
    app.instance_path = str(tmp_path)
    with app.app_context():
        db.create_all()
        u = Usuario(nome="Equipe", login="equipe")
        u.definir_senha("senha-forte")
        a = Associado(numero_socio="0142", nome="Ana Já Cadastrada", cpf=CPF_EXISTENTE, data_inscricao=date(2019, 3, 10))
        a.criar_checklist()
        db.session.add_all([u, a])
        db.session.commit()
    yield app


@pytest.fixture
def cliente(app):
    c = app.test_client()
    c.post("/login", data={"login": "equipe", "senha": "senha-forte"})
    return c


def planilha_xlsx(linhas, cabecalho=("Nº de sócio", "Nome completo", "CPF", "Data de inscrição", "Categoria", "Celular (WhatsApp)")):
    livro = Workbook()
    aba = livro.active
    aba.append(list(cabecalho))
    for linha in linhas:
        aba.append(list(linha))
    saida = io.BytesIO()
    livro.save(saida)
    saida.seek(0)
    return saida


def enviar(cliente, arquivo, nome="associados.xlsx"):
    r = cliente.post("/importar/", data={"planilha": (arquivo, nome)}, content_type="multipart/form-data")
    return r


def test_modelo_baixa_com_as_colunas(cliente):
    r = cliente.get("/importar/modelo.xlsx")
    assert r.status_code == 200
    aba = load_workbook(io.BytesIO(r.data)).worksheets[0]
    assert [c.value for c in aba[1]][:3] == ["Nº de sócio", "Nome completo", "CPF"]


def test_previa_aponta_erros_e_nao_grava_nada(app, cliente):
    arquivo = planilha_xlsx([
        ("0200", "Maria Pronta", "286.139.540-06", "10/01/2020", "mutirante", "(11) 90000-0200"),
        ("", "João Sem Número", 11144477735.0, datetime(2021, 5, 2), "", ""),     # CPF como número e data do Excel
        ("", "Zeros Perdidos", 1234567890, "", "regular", ""),                     # Excel apagou o 0 do CPF
        ("0201", "CPF Errado", "123.456.789-00", "", "", ""),
        ("0202", "Repetido Na Planilha", "28613954006", "", "", ""),
        ("0203", "Já Existe", CPF_EXISTENTE, "", "", ""),
        ("0142", "Número Em Uso", "71460238001", "", "", ""),
        ("0204", "Data Ruim", "12312312387", "31/02/2020", "", ""),
        ("0205", "", "98765432100", "", "", ""),
    ])
    r = enviar(cliente, arquivo)
    assert "/importar/" in r.headers["Location"]
    pagina = cliente.get(r.headers["Location"]).get_data(as_text=True)
    assert "3 pronta(s)" in pagina and "6 com erro" in pagina
    for erro in ["CPF inválido", "CPF repetido (linha 2)", "CPF já cadastrado", "nº 0142 já está em uso", "data inválida", "sem nome"]:
        assert erro in pagina
    with app.app_context():
        assert db.session.execute(db.select(db.func.count()).select_from(Associado)).scalar() == 1


def test_confirmar_importa_as_prontas_e_numera_as_sem_numero(app, cliente):
    arquivo = planilha_xlsx([
        ("0200", "Maria Pronta", "286.139.540-06", "10/01/2020", "Mutirante", "(11) 90000-0200"),
        ("", "João Sem Número", "111.444.777-35", "", "", ""),
        ("0201", "CPF Errado", "123.456.789-00", "", "", ""),
    ])
    previa = enviar(cliente, arquivo).headers["Location"]
    token = previa.rstrip("/").split("/")[-1]
    r = cliente.post(f"/importar/{token}/confirmar", data={"fichas_assinadas": "1"}, follow_redirects=True)
    assert "2 associado(s) importado(s)" in r.get_data(as_text=True)
    with app.app_context():
        maria = db.session.execute(db.select(Associado).filter_by(cpf="28613954006")).scalar_one()
        joao = db.session.execute(db.select(Associado).filter_by(cpf="11144477735")).scalar_one()
        assert maria.numero_socio == "0200" and maria.categoria == "mutirante" and maria.data_inscricao == date(2020, 1, 10)
        assert maria.consentimento_lgpd_em and len(maria.documentos) == 5 and maria.qr_codigo
        assert joao.numero_socio == "0201"  # próximo depois do maior (0200)
    assert not os.listdir(os.path.join(app.instance_path, "importacoes"))  # arquivo temporário apagado


def test_csv_do_excel_brasileiro(app, cliente):
    texto = "Nome completo;CPF;Categoria\nJosé Acentuação;390.533.447-05;mutirante\n"
    r = enviar(cliente, io.BytesIO(texto.encode("cp1252")), "associados.csv")
    pagina = cliente.get(r.headers["Location"]).get_data(as_text=True)
    assert "José Acentuação" in pagina and "1 pronta(s)" in pagina


def test_planilha_sem_coluna_cpf_e_recusada(cliente):
    r = enviar(cliente, planilha_xlsx([("Fulano",)], cabecalho=("Nome completo",)))
    assert r.headers["Location"].endswith("/importar/")
    assert "precisa ter as colunas" in cliente.get("/importar/").get_data(as_text=True)


def test_cancelar_apaga_a_previa(app, cliente):
    previa = enviar(cliente, planilha_xlsx([("", "Teste", "390.533.447-05", "", "", "")])).headers["Location"]
    token = previa.rstrip("/").split("/")[-1]
    cliente.post(f"/importar/{token}/cancelar")
    assert cliente.get(f"/importar/{token}").status_code == 404


def test_codigos_em_lote_nao_trocam_codigo_valido(app, cliente):
    with app.app_context():
        for numero, cpf in [("0300", "28613954006"), ("0301", "11144477735"), ("0302", "39053344705")]:
            db.session.add(Associado(numero_socio=numero, nome=f"Teste {numero}", cpf=cpf, celular="11900000000"))
        db.session.commit()
        valido = db.session.execute(db.select(Associado).filter_by(numero_socio="0300")).scalar_one()
        valido.codigo_acesso, valido.codigo_expira_em = "ABCDEF", datetime.now() + timedelta(days=3)
        vencido = db.session.execute(db.select(Associado).filter_by(numero_socio="0301")).scalar_one()
        vencido.codigo_acesso, vencido.codigo_expira_em = "VENCID", datetime.now() - timedelta(days=1)
        com_senha = db.session.execute(db.select(Associado).filter_by(numero_socio="0302")).scalar_one()
        com_senha.definir_senha("senha123")
        db.session.commit()
    r = cliente.post("/acessos/gerar", follow_redirects=True)
    assert "2 código(s) gerado(s)" in r.get_data(as_text=True)  # Ana (sem código) + o vencido
    with app.app_context():
        get = lambda n: db.session.execute(db.select(Associado).filter_by(numero_socio=n)).scalar_one()
        assert get("0300").codigo_acesso == "ABCDEF"
        assert get("0301").codigo_acesso != "VENCID" and get("0301").codigo_expira_em > datetime.now()
        assert get("0302").codigo_acesso is None
        assert get("0142").codigo_acesso
    pagina = cliente.get("/acessos/?filtro=codigo_enviado").get_data(as_text=True)
    assert "Enviar pelo WhatsApp" in pagina and "ABCDEF" in pagina
