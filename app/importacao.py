"""Importação dos associados por planilha (Excel .xlsx ou .csv), com prévia antes de gravar.

Fluxo: baixar o modelo → preencher → enviar → conferir a prévia (linha a linha) → confirmar.
Nada é gravado no cadastro antes da confirmação.
"""
import csv
import io
import json
import os
import unicodedata
import uuid
from datetime import date, datetime

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required

from . import db
from .models import Associado, novo_codigo_qr
from .utils import cpf_valido, formatar_cpf, ler_data, somente_digitos

bp = Blueprint("importacao", __name__, url_prefix="/importar")

MAX_LINHAS = 3000

# coluna do modelo -> campo do sistema. Os nomes das colunas são reconhecidos sem acento e sem maiúsculas.
COLUNAS = [
    ("Nº de sócio", "numero_socio", "4 dígitos. Se deixar em branco, o sistema numera em sequência."),
    ("Nome completo", "nome", "Obrigatório."),
    ("CPF", "cpf", "Obrigatório. Com ou sem pontos."),
    ("Data de inscrição", "data_inscricao", "dd/mm/aaaa. Em branco = hoje."),
    ("Categoria", "categoria", "regular ou mutirante. Em branco = regular."),
    ("Celular (WhatsApp)", "celular", "Com DDD."),
    ("Data de nascimento", "data_nascimento", "dd/mm/aaaa."),
    ("RG", "rg", ""),
    ("E-mail", "email", ""),
    ("Rua", "rua", ""),
    ("Número", "numero", ""),
    ("Bairro", "bairro", ""),
    ("Cidade", "cidade", "Em branco = Embu das Artes."),
    ("UF", "uf", "Em branco = SP."),
    ("CEP", "cep", ""),
]
SINONIMOS = {
    "n de socio": "numero_socio", "no de socio": "numero_socio", "numero de socio": "numero_socio",
    "numero socio": "numero_socio", "socio": "numero_socio", "matricula": "numero_socio",
    "nome": "nome", "nome do titular": "nome", "titular": "nome",
    "inscricao": "data_inscricao", "data inscricao": "data_inscricao",
    "grupo": "categoria", "celular": "celular", "whatsapp": "celular", "telefone": "celular",
    "nascimento": "data_nascimento", "email": "email", "endereco": "rua", "logradouro": "rua",
    "n": "numero", "no": "numero",
}


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    texto = "".join(c if c.isalnum() else " " for c in texto.lower())
    return " ".join(texto.split())


MAPA = {normalizar(rotulo): campo for rotulo, campo, _ in COLUNAS}
MAPA.update(SINONIMOS)


def campo_da_coluna(cabecalho):
    chave = normalizar(cabecalho)
    if chave in MAPA:
        return MAPA[chave]
    for nome, campo in MAPA.items():  # ex.: "Categoria (regular ou mutirante)"
        if len(nome) > 3 and chave.startswith(nome):
            return campo
    return None


def pasta_importacoes():
    pasta = os.path.join(current_app.instance_path, "importacoes")
    os.makedirs(pasta, exist_ok=True)
    return pasta


# ---------- leitura do arquivo ----------

def ler_planilha(arquivo):
    """Devolve (cabeçalhos, linhas) de um .xlsx ou .csv. Linhas = listas de valores."""
    nome = (arquivo.filename or "").lower()
    conteudo = arquivo.read()
    if nome.endswith(".xlsx"):
        from openpyxl import load_workbook

        planilha = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True).worksheets[0]
        todas = [list(linha) for linha in planilha.iter_rows(values_only=True)]
    elif nome.endswith(".csv"):
        for codificacao in ("utf-8-sig", "cp1252"):
            try:
                texto = conteudo.decode(codificacao)
                break
            except UnicodeDecodeError:
                continue
        primeira = texto.splitlines()[0] if texto else ""
        separador = ";" if primeira.count(";") >= primeira.count(",") else ","
        todas = [linha for linha in csv.reader(io.StringIO(texto), delimiter=separador)]
    else:
        raise ValueError("Envie a planilha em Excel (.xlsx) ou CSV (.csv).")
    todas = [l for l in todas if any(str(v).strip() for v in l if v is not None)]
    if not todas:
        raise ValueError("A planilha está vazia.")
    return todas[0], todas[1:]


def texto_da_celula(valor):
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))  # Excel guarda CPF e nº como número: 52998224725.0
    return str(valor).strip()


def analisar(cabecalhos, linhas):
    """Valida cada linha sem gravar nada. Devolve (resultado por linha, colunas não reconhecidas)."""
    campos = [campo_da_coluna(c) for c in cabecalhos]
    ignoradas = [str(c) for c, campo in zip(cabecalhos, campos) if campo is None and str(c or "").strip()]
    if "nome" not in campos or "cpf" not in campos:
        raise ValueError("A planilha precisa ter as colunas \"Nome completo\" e \"CPF\". Use o modelo.")
    if len(linhas) > MAX_LINHAS:
        raise ValueError(f"A planilha tem mais de {MAX_LINHAS} linhas. Divida em partes.")

    cpfs_banco = set(db.session.execute(db.select(Associado.cpf)).scalars())
    numeros_banco = set(db.session.execute(db.select(Associado.numero_socio)).scalars())
    cpfs_planilha, numeros_planilha, resultado = {}, {}, []

    for indice, linha in enumerate(linhas, start=2):  # linha 1 = cabeçalho
        dados = {}
        for campo, valor in zip(campos, linha):
            if campo:
                dados[campo] = texto_da_celula(valor)
        erros = []
        nome = " ".join(dados.get("nome", "").split())
        cpf = somente_digitos(dados.get("cpf"))
        if len(cpf) in (9, 10):
            cpf = cpf.zfill(11)  # Excel apaga os zeros do começo do CPF
        numero = somente_digitos(dados.get("numero_socio"))
        numero = numero.zfill(4) if numero else ""
        if not nome:
            erros.append("sem nome")
        if not cpf_valido(cpf):
            erros.append("CPF inválido")
        elif cpf in cpfs_banco:
            erros.append("CPF já cadastrado no sistema")
        elif cpf in cpfs_planilha:
            erros.append(f"CPF repetido (linha {cpfs_planilha[cpf]})")
        if numero:
            if numero in numeros_banco:
                erros.append(f"nº {numero} já está em uso")
            elif numero in numeros_planilha:
                erros.append(f"nº {numero} repetido (linha {numeros_planilha[numero]})")
        datas = {}
        for campo in ("data_inscricao", "data_nascimento"):
            try:
                datas[campo] = ler_data(dados.get(campo))
            except ValueError:
                erros.append(f"data inválida em {'inscrição' if campo == 'data_inscricao' else 'nascimento'}")
                datas[campo] = None
        categoria = "mutirante" if normalizar(dados.get("categoria")).startswith("mut") else "regular"
        if not erros:
            cpfs_planilha[cpf] = indice
            if numero:
                numeros_planilha[numero] = indice
        resultado.append({
            "linha": indice,
            "erros": erros,
            "numero_socio": numero,
            "nome": nome,
            "cpf": cpf,
            "categoria": categoria,
            "data_inscricao": datas["data_inscricao"].isoformat() if datas["data_inscricao"] else "",
            "data_nascimento": datas["data_nascimento"].isoformat() if datas["data_nascimento"] else "",
            "celular": dados.get("celular", ""),
            "rg": dados.get("rg", ""),
            "email": dados.get("email", ""),
            "rua": dados.get("rua", ""),
            "numero": dados.get("numero", ""),
            "bairro": dados.get("bairro", ""),
            "cidade": dados.get("cidade", "") or "Embu das Artes",
            "uf": (dados.get("uf", "") or "SP")[:2].upper(),
            "cep": somente_digitos(dados.get("cep"))[:8],
        })
    return resultado, ignoradas


# ---------- telas ----------

@bp.route("/", methods=["GET", "POST"])
@login_required
def inicio():
    if request.method == "POST":
        arquivo = request.files.get("planilha")
        if not arquivo or not arquivo.filename:
            flash("Escolha a planilha.", "erro")
            return redirect(url_for("importacao.inicio"))
        try:
            cabecalhos, linhas = ler_planilha(arquivo)
            resultado, ignoradas = analisar(cabecalhos, linhas)
        except ValueError as erro:
            flash(str(erro), "erro")
            return redirect(url_for("importacao.inicio"))
        except Exception:  # arquivo corrompido ou protegido por senha
            flash("Não foi possível ler a planilha. Salve de novo como .xlsx ou .csv e tente outra vez.", "erro")
            return redirect(url_for("importacao.inicio"))
        token = uuid.uuid4().hex
        with open(os.path.join(pasta_importacoes(), f"{token}.json"), "w", encoding="utf-8") as f:
            json.dump({"arquivo": arquivo.filename, "linhas": resultado, "ignoradas": ignoradas}, f, ensure_ascii=False)
        return redirect(url_for("importacao.previa", token=token))
    return render_template("importacao/inicio.html", colunas=COLUNAS)


def carregar(token):
    if not token.isalnum():
        abort(404)
    caminho = os.path.join(pasta_importacoes(), f"{token}.json")
    if not os.path.exists(caminho):
        abort(404)
    with open(caminho, encoding="utf-8") as f:
        return caminho, json.load(f)


@bp.route("/<token>")
@login_required
def previa(token):
    _, dados = carregar(token)
    linhas = dados["linhas"]
    validas = [l for l in linhas if not l["erros"]]
    return render_template("importacao/previa.html", token=token, dados=dados, linhas=linhas,
                           validas=validas, formatar_cpf=formatar_cpf)


@bp.route("/<token>/confirmar", methods=["POST"])
@login_required
def confirmar(token):
    caminho, dados = carregar(token)
    from .associados import proximo_numero

    # valida de novo: alguém pode ter cadastrado associados enquanto a prévia estava aberta
    cpfs = set(db.session.execute(db.select(Associado.cpf)).scalars())
    numeros = set(db.session.execute(db.select(Associado.numero_socio)).scalars())
    consentimento = datetime.now() if request.form.get("fichas_assinadas") else None
    criados, pulados = 0, 0
    sem_numero = []
    for l in dados["linhas"]:
        if l["erros"] or l["cpf"] in cpfs or (l["numero_socio"] and l["numero_socio"] in numeros):
            pulados += 1
            continue
        a = Associado(
            numero_socio=l["numero_socio"] or None, nome=l["nome"], cpf=l["cpf"], categoria=l["categoria"],
            data_inscricao=date.fromisoformat(l["data_inscricao"]) if l["data_inscricao"] else date.today(),
            data_nascimento=date.fromisoformat(l["data_nascimento"]) if l["data_nascimento"] else None,
            celular=l["celular"] or None, rg=l["rg"] or None, email=l["email"] or None, rua=l["rua"] or None,
            numero=l["numero"] or None, bairro=l["bairro"] or None, cidade=l["cidade"], uf=l["uf"],
            cep=l["cep"] or None, qr_codigo=novo_codigo_qr(), consentimento_lgpd_em=consentimento,
        )
        a.criar_checklist()
        if a.numero_socio:
            numeros.add(a.numero_socio)
            db.session.add(a)
        else:
            sem_numero.append(a)
        cpfs.add(l["cpf"])
        criados += 1
    db.session.flush()
    for a in sem_numero:  # numera depois, para não pegar um nº que vem mais abaixo na planilha
        a.numero_socio = proximo_numero()
        db.session.add(a)
        db.session.flush()
    db.session.commit()
    os.remove(caminho)
    flash(f"{criados} associado(s) importado(s)." + (f" {pulados} linha(s) com erro ficaram de fora." if pulados else "")
          + " Próximo passo: gerar os códigos de acesso.", "ok")
    return redirect(url_for("acessos.lista"))


@bp.route("/<token>/cancelar", methods=["POST"])
@login_required
def cancelar(token):
    caminho, _ = carregar(token)
    os.remove(caminho)
    flash("Importação cancelada. Nada foi gravado.", "aviso")
    return redirect(url_for("importacao.inicio"))


@bp.route("/modelo.xlsx")
@login_required
def modelo():
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    livro = Workbook()
    aba = livro.active
    aba.title = "Associados"
    aba.append([rotulo for rotulo, _, _ in COLUNAS])
    aba.append(["0001", "Nome Fictício de Exemplo (apague esta linha)", "529.982.247-25", "10/03/2019", "regular",
                "(11) 90000-0000", "01/01/1980", "", "", "Rua Juquitiba", "92", "Jardim Nayara", "Embu das Artes",
                "SP", "06800-000"])
    for celula in aba[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="2B3F8F")
        celula.alignment = Alignment(wrap_text=True, vertical="center")
    for coluna in aba.columns:
        aba.column_dimensions[coluna[0].column_letter].width = 22
    aba.column_dimensions["B"].width = 40
    for linha in aba.iter_rows(min_row=2, max_row=600):
        for celula in linha:
            celula.number_format = "@"  # texto: o Excel não apaga zeros do CPF e do nº
    aba.freeze_panes = "A2"
    ajuda = livro.create_sheet("Como preencher")
    ajuda.append(["Coluna", "Como preencher"])
    for rotulo, _, explicacao in COLUNAS:
        ajuda.append([rotulo, explicacao])
    ajuda.append([])
    ajuda.append(["Dica", "Uma linha por associado titular. Familiares, documentos e foto são completados depois, na ficha."])
    ajuda.column_dimensions["A"].width = 24
    ajuda.column_dimensions["B"].width = 80
    for celula in ajuda[1]:
        celula.font = Font(bold=True)
    saida = io.BytesIO()
    livro.save(saida)
    saida.seek(0)
    return send_file(saida, as_attachment=True, download_name="modelo-associados-vila-das-artes.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
