"""Mensalidades: a mensalidade só fica PAGA depois que a equipe valida o comprovante."""
import os
import uuid
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func

from . import db
from .models import Associado, Configuracao, Mensalidade
from .regras import (
    CHAVE_COBRANCA_MUTIRANTES,
    competencia_atual,
    garantir_mensalidades,
    proximo_recibo,
)

bp = Blueprint("mensalidades", __name__, url_prefix="/mensalidades")

EXTENSOES = {"jpg", "jpeg", "png", "pdf", "webp"}
MOTIVOS_RECUSA = (
    "Valor diferente de R$ 50,00",
    "Comprovante ilegível",
    "Comprovante de outro mês",
    "Pagamento não localizado",
    "Outro",
)


def pasta_comprovantes():
    pasta = os.path.join(current_app.instance_path, "comprovantes")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def salvar_comprovante(arquivo):
    """Guarda o arquivo com nome aleatório (nunca o nome original) e devolve o nome salvo."""
    if not arquivo or not arquivo.filename:
        return None, "Anexe a foto ou o PDF do comprovante."
    extensao = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if extensao not in EXTENSOES:
        return None, "Formato não aceito. Use foto (JPG/PNG) ou PDF."
    if extensao == "pdf":
        nome = f"{uuid.uuid4().hex}.pdf"
        arquivo.save(os.path.join(pasta_comprovantes(), nome))
        return nome, None
    # Foto: reduz para no máximo 1600 px e salva em JPG (cabe muito mais no servidor e apaga a localização da foto)
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        imagem = ImageOps.exif_transpose(Image.open(arquivo.stream))
    except (UnidentifiedImageError, OSError):
        return None, "Não foi possível abrir a imagem. Tire a foto de novo ou envie em PDF."
    imagem.thumbnail((1600, 1600))
    nome = f"{uuid.uuid4().hex}.jpg"
    imagem.convert("RGB").save(os.path.join(pasta_comprovantes(), nome), "JPEG", quality=80, optimize=True)
    return nome, None


def buscar(mensalidade_id):
    m = db.session.get(Mensalidade, mensalidade_id)
    if not m:
        abort(404)
    return m


def mes_valido(texto):
    try:
        datetime.strptime(texto, "%Y-%m")
        return True
    except (TypeError, ValueError):
        return False


@bp.route("/")
@login_required
def mes():
    competencia = request.args.get("mes") or competencia_atual()
    if not mes_valido(competencia):
        competencia = competencia_atual()
    garantir_mensalidades(competencia)

    filtro = request.args.get("filtro", "todas")
    base = db.select(Mensalidade).join(Associado).filter(Mensalidade.competencia == competencia)
    if filtro in ("aberta", "em_analise", "paga", "recusada", "isenta"):
        base = base.filter(Mensalidade.status == filtro)
    lista = db.session.execute(base.order_by(Associado.numero_socio)).scalars().all()

    contagem = dict(
        db.session.execute(
            db.select(Mensalidade.status, func.count())
            .filter_by(competencia=competencia)
            .group_by(Mensalidade.status)
        ).all()
    )
    fila = db.session.execute(
        db.select(Mensalidade)
        .filter_by(status="em_analise")
        .order_by(Mensalidade.enviado_em)
    ).scalars().all()

    ano, m = map(int, competencia.split("-"))
    meses_menu = []
    for i in range(-6, 2):
        total = ano * 12 + (m - 1) + i
        meses_menu.append(f"{total // 12:04d}-{total % 12 + 1:02d}")

    cobrados = sum(v for k, v in contagem.items() if k != "isenta")
    return render_template(
        "mensalidades/mes.html",
        competencia=competencia,
        lista=lista,
        contagem=contagem,
        cobrados=cobrados,
        fila=fila,
        filtro=filtro,
        meses_menu=meses_menu,
        motivos_recusa=MOTIVOS_RECUSA,
        cobranca_desde=Configuracao.obter(CHAVE_COBRANCA_MUTIRANTES),
    )


def registrar_recebimento(m, forma, arquivo):
    """Registra pagamento recebido pela equipe: em dinheiro (sem arquivo) ou com foto/PDF do comprovante.

    Fica "em análise" até a administração conferir. Devolve uma mensagem de erro ou None.
    """
    if m.status in ("paga", "isenta"):
        return "Esta mensalidade já está paga ou é isenta."
    if m.status == "em_analise":
        return "Esta mensalidade já foi recebida e está aguardando a conferência."
    nome = None
    if forma == "dinheiro":
        if arquivo and arquivo.filename:  # foto do recibo em papel, se houver
            nome, erro = salvar_comprovante(arquivo)
            if erro:
                return erro
    else:
        forma = "pix"
        nome, erro = salvar_comprovante(arquivo)
        if erro:
            return erro
    m.comprovante = nome
    m.forma = forma
    m.status = "em_analise"
    m.enviado_em = datetime.now()
    m.registrado_por_id = current_user.id
    m.motivo_recusa = None
    db.session.commit()
    return None


@bp.route("/receber")
@login_required
def receber():
    """Coleta na assembleia: pelo nº de sócio (ou QR), mostra as mensalidades em aberto para receber."""
    from .assembleias import buscar_por_codigo

    codigo = (request.args.get("codigo") or "").strip()
    associado, mensalidades = None, []
    if codigo:
        associado, _ = buscar_por_codigo(codigo)
        if not associado:
            flash(f"Nº ou QR “{codigo}” não encontrado.", "erro")
        elif associado.situacao != "ativo":
            flash(f"{associado.nome} não está ativo(a).", "erro")
            associado = None
        else:
            garantir_mensalidades(competencia_atual())
            mensalidades = sorted(
                (m for m in associado.mensalidades if m.status in ("aberta", "recusada", "em_analise")),
                key=lambda m: m.competencia,
            )
    return render_template("mensalidades/receber.html", codigo=codigo, a=associado, mensalidades=mensalidades,
                           voltar=request.args.get("voltar", ""))


@bp.route("/<int:mensalidade_id>/receber", methods=["POST"])
@login_required
def receber_mensalidade(mensalidade_id):
    m = buscar(mensalidade_id)
    erro = registrar_recebimento(m, request.form.get("forma"), request.files.get("comprovante"))
    if erro:
        flash(erro, "erro")
    elif m.forma == "dinheiro":
        flash(f"Recebido em dinheiro: {m.mes_ano} de {m.associado.nome}. A administração confere o valor no caixa.", "ok")
    else:
        flash(f"Comprovante de {m.mes_ano} de {m.associado.nome} registrado. A administração confere.", "ok")
    voltar = request.form.get("voltar", "")
    return redirect(url_for("mensalidades.receber", codigo=m.associado.numero_socio, voltar=voltar))


@bp.route("/<int:mensalidade_id>/comprovante", methods=["POST"])
@login_required
def registrar_comprovante(mensalidade_id):
    """Equipe registra um comprovante entregue na sede. Fica 'em análise' até alguém validar."""
    m = buscar(mensalidade_id)
    erro = registrar_recebimento(m, request.form.get("forma"), request.files.get("comprovante"))
    if erro:
        flash(erro, "erro")
        return redirect(url_for("mensalidades.mes", mes=m.competencia))
    flash(f"Pagamento de {m.associado.nome} registrado. Agora falta a conferência.", "ok")
    return redirect(url_for("mensalidades.mes", mes=m.competencia) + "#fila")


@bp.route("/<int:mensalidade_id>/validar", methods=["POST"])
@login_required
def validar(mensalidade_id):
    m = buscar(mensalidade_id)
    if m.status != "em_analise" or not (m.comprovante or m.forma == "dinheiro"):
        flash("Só dá para validar uma mensalidade em análise, com comprovante ou recebida em dinheiro.", "erro")
        return redirect(url_for("mensalidades.mes", mes=m.competencia))
    m.status = "paga"
    m.validado_por_id = current_user.id
    m.validado_em = datetime.now()
    m.numero_recibo = proximo_recibo(m.competencia)
    db.session.commit()
    flash(f"Mensalidade de {m.associado.nome} validada. Recibo nº {m.numero_recibo}.", "ok")
    return redirect(request.form.get("voltar") or url_for("mensalidades.mes", mes=m.competencia) + "#fila")


@bp.route("/<int:mensalidade_id>/recusar", methods=["POST"])
@login_required
def recusar(mensalidade_id):
    m = buscar(mensalidade_id)
    motivo = request.form.get("motivo", "").strip()
    if m.status != "em_analise":
        flash("Só dá para recusar uma mensalidade em análise.", "erro")
    elif not motivo:
        flash("Escolha o motivo da recusa.", "erro")
    else:
        m.status = "recusada"
        m.motivo_recusa = motivo[:200]
        m.validado_por_id = current_user.id
        m.validado_em = datetime.now()
        db.session.commit()
        flash(f"Comprovante de {m.associado.nome} recusado: {motivo}. Avise o associado.", "aviso")
    return redirect(request.form.get("voltar") or url_for("mensalidades.mes", mes=m.competencia) + "#fila")


@bp.route("/<int:mensalidade_id>/arquivo")
@login_required
def arquivo(mensalidade_id):
    m = buscar(mensalidade_id)
    if not m.comprovante:
        abort(404)
    return send_from_directory(pasta_comprovantes(), m.comprovante)


@bp.route("/<int:mensalidade_id>/recibo")
@login_required
def recibo(mensalidade_id):
    m = buscar(mensalidade_id)
    if m.status != "paga":
        abort(404)
    return render_template("mensalidades/recibo.html", m=m)


@bp.route("/cobranca-mutirantes", methods=["POST"])
@login_required
def cobranca_mutirantes():
    """Quando sair um novo projeto do CDHU, a diretoria ativa a cobrança dos mutirantes."""
    acao = request.form.get("acao")
    if acao == "ativar":
        desde = request.form.get("desde", "")
        if not mes_valido(desde):
            flash("Escolha o mês de início da cobrança.", "erro")
            return redirect(url_for("mensalidades.mes"))
        Configuracao.definir(CHAVE_COBRANCA_MUTIRANTES, desde)
        # mensalidades isentas a partir desse mês passam a ser cobradas
        for m in db.session.execute(
            db.select(Mensalidade).join(Associado).filter(
                Associado.categoria == "mutirante",
                Mensalidade.status == "isenta",
                Mensalidade.competencia >= desde,
            )
        ).scalars():
            m.status = "aberta"
        db.session.commit()
        flash(f"Cobrança dos mutirantes ativada a partir de {desde[5:]}/{desde[:4]}.", "ok")
    elif acao == "desativar":
        Configuracao.definir(CHAVE_COBRANCA_MUTIRANTES, None)
        db.session.commit()
        flash("Cobrança dos mutirantes desativada. As próximas mensalidades deles voltam a ser isentas.", "ok")
    return redirect(url_for("mensalidades.mes"))
