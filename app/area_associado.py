"""Área do associado: acesso pelo celular, termo de uso de dados e imagem, foto, carteirinha e comprovantes."""
import os
import secrets
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from PIL import Image, ImageOps, UnidentifiedImageError

from . import db, termo
from .models import Assembleia, Associado, Mensalidade
from .regras import competencia_atual, garantir_mensalidades, proxima_assembleia, situacao
from .seguranca import bloqueado, limpar, registrar_falha
from .utils import cpf_valido, somente_digitos

bp = Blueprint("area", __name__, url_prefix="/associado")

CHAVE = "associado_id"
LETRAS_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O e 1/I para não confundir


# ---------- utilidades ----------

def pasta_fotos():
    pasta = os.path.join(current_app.instance_path, "fotos")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def gerar_codigo_acesso(associado, dias=7):
    """Código de primeiro acesso (ou para trocar a senha), gerado pela equipe."""
    codigo = "".join(secrets.choice(LETRAS_CODIGO) for _ in range(6))
    associado.codigo_acesso = codigo
    associado.codigo_expira_em = datetime.now() + timedelta(days=dias)
    return codigo


def salvar_foto(associado, arquivo):
    """Recorta em quadrado, reduz para 600 px e salva como JPG (remove dados ocultos da foto, como localização)."""
    if not arquivo or not arquivo.filename:
        return "Escolha uma foto."
    try:
        imagem = Image.open(arquivo.stream)
        imagem = ImageOps.exif_transpose(imagem).convert("RGB")
    except (UnidentifiedImageError, OSError):
        return "Não foi possível ler a imagem. Envie uma foto JPG ou PNG."
    lado = min(imagem.size)
    esquerda, topo = (imagem.width - lado) // 2, (imagem.height - lado) // 2
    imagem = imagem.crop((esquerda, topo, esquerda + lado, topo + lado)).resize((600, 600))
    nome = f"{uuid.uuid4().hex}.jpg"
    imagem.save(os.path.join(pasta_fotos(), nome), "JPEG", quality=85)
    apagar_foto(associado)
    associado.foto = nome
    associado.foto_enviada_em = datetime.now()
    return None


def apagar_foto(associado):
    if associado.foto:
        caminho = os.path.join(pasta_fotos(), associado.foto)
        if os.path.exists(caminho):
            os.remove(caminho)
    associado.foto = None
    associado.foto_enviada_em = None


def associado_logado():
    associado_id = session.get(CHAVE)
    if not associado_id:
        return None
    associado = db.session.get(Associado, associado_id)
    if not associado or associado.situacao != "ativo" or not associado.tem_acesso:
        session.pop(CHAVE, None)
        return None
    return associado


def precisa_aceitar_termo(associado):
    return associado.termo_versao != termo.VERSAO or not associado.termo_aceito_em


def associado_required(view):
    @wraps(view)
    def envolvido(*args, **kwargs):
        associado = associado_logado()
        if not associado:
            return redirect(url_for("area.entrar"))
        if precisa_aceitar_termo(associado) and request.endpoint not in ("area.termo", "area.sair"):
            return redirect(url_for("area.termo"))
        return view(associado, *args, **kwargs)

    return envolvido


def chave_bloqueio(cpf):
    return "associado:" + (somente_digitos(cpf or "")[:11] or "vazio")


def buscar_por_cpf(cpf):
    cpf = somente_digitos(cpf)
    if not cpf_valido(cpf):
        return None
    return db.session.execute(db.select(Associado).filter_by(cpf=cpf, situacao="ativo")).scalar_one_or_none()


# ---------- entrar, primeiro acesso, sair ----------

@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    if associado_logado():
        return redirect(url_for("area.inicio"))
    if request.method == "POST":
        chave = chave_bloqueio(request.form.get("cpf"))
        if bloqueado(chave):
            flash("Muitas tentativas. Aguarde 15 minutos e tente de novo.", "erro")
            return render_template("area/entrar.html")
        associado = buscar_por_cpf(request.form.get("cpf"))
        if associado and associado.conferir_senha(request.form.get("senha", "")):
            limpar(chave)
            session[CHAVE] = associado.id
            return redirect(url_for("area.inicio"))
        registrar_falha(chave)
        flash("CPF ou senha incorretos. Se é seu primeiro acesso, peça o código para a equipe.", "erro")
    return render_template("area/entrar.html")


@bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    if request.method == "POST":
        chave = chave_bloqueio(request.form.get("cpf"))
        if bloqueado(chave):
            flash("Muitas tentativas. Aguarde 15 minutos e tente de novo.", "erro")
            return render_template("area/primeiro_acesso.html")
        associado = buscar_por_cpf(request.form.get("cpf"))
        codigo = request.form.get("codigo", "").strip().upper()
        senha = request.form.get("senha", "")
        valido = (
            associado
            and associado.codigo_acesso
            and associado.codigo_expira_em
            and associado.codigo_expira_em > datetime.now()
            and secrets.compare_digest(associado.codigo_acesso, codigo)
        )
        if not valido:
            registrar_falha(chave)
            flash("CPF ou código inválido ou vencido. Peça um novo código para a equipe.", "erro")
        elif len(senha) < 6:
            flash("A senha precisa ter pelo menos 6 caracteres.", "erro")
        elif senha != request.form.get("confirmar"):
            flash("As senhas não são iguais.", "erro")
        else:
            associado.definir_senha(senha)
            associado.codigo_acesso = None
            associado.codigo_expira_em = None
            db.session.commit()
            limpar(chave)
            session[CHAVE] = associado.id
            flash("Senha criada! Agora leia e aceite o termo de uso dos dados.", "ok")
            return redirect(url_for("area.termo"))
    return render_template("area/primeiro_acesso.html")


@bp.route("/sair", methods=["POST"])
def sair():
    session.pop(CHAVE, None)
    flash("Você saiu da área do associado.", "ok")
    return redirect(url_for("area.entrar"))


# ---------- termo ----------

@bp.route("/termo", endpoint="termo", methods=["GET", "POST"])
@associado_required
def termo_view(associado):
    if request.method == "POST":
        if not request.form.get("aceite_dados"):
            flash("Para usar a área do associado é preciso aceitar o uso dos dados.", "erro")
        else:
            associado.termo_aceito_em = datetime.now()
            associado.termo_versao = termo.VERSAO
            if request.form.get("aceite_imagem"):
                associado.imagem_autorizada_em = associado.imagem_autorizada_em or datetime.now()
            else:
                associado.imagem_autorizada_em = None
                apagar_foto(associado)  # sem autorização de imagem, a foto não fica guardada
            db.session.commit()
            flash("Termo aceito. Obrigado!", "ok")
            return redirect(url_for("area.inicio"))
    return render_template("area/termo.html", a=associado, termo=termo)



# ---------- início, foto e comprovantes ----------

@bp.route("/")
@associado_required
def inicio(associado):
    garantir_mensalidades(competencia_atual())
    inscricao = associado.data_inscricao or associado.criado_em.date()
    assembleias = db.session.execute(
        db.select(Assembleia).filter(Assembleia.data >= inscricao).order_by(Assembleia.data.desc()).limit(3)
    ).scalars().all()
    return render_template(
        "area/inicio.html",
        a=associado,
        s=situacao(associado),
        proxima=proxima_assembleia(),
        assembleias=assembleias,
        presentes={p.assembleia_id for p in associado.presencas},
    )


@bp.route("/foto", methods=["POST"])
@associado_required
def enviar_foto(associado):
    if not associado.imagem_autorizada_em:
        flash("Para enviar a foto, autorize o uso da imagem no termo.", "erro")
        return redirect(url_for("area.termo"))
    erro = salvar_foto(associado, request.files.get("foto"))
    if erro:
        flash(erro, "erro")
    else:
        db.session.commit()
        flash("Foto atualizada!", "ok")
    return redirect(url_for("area.inicio"))


@bp.route("/foto/remover", methods=["POST"])
@associado_required
def remover_foto(associado):
    apagar_foto(associado)
    db.session.commit()
    flash("Foto removida.", "ok")
    return redirect(url_for("area.inicio"))


@bp.route("/foto.jpg")
@associado_required
def minha_foto(associado):
    if not associado.foto:
        abort(404)
    return send_from_directory(pasta_fotos(), associado.foto)


@bp.route("/qr.png")
@associado_required
def meu_qr(associado):
    import io

    import qrcode
    from flask import send_file

    buffer = io.BytesIO()
    qrcode.make(associado.qr_codigo, box_size=8, border=2).save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@bp.route("/mensalidades/<int:mensalidade_id>/comprovante", methods=["POST"])
@associado_required
def enviar_comprovante(associado, mensalidade_id):
    from .mensalidades import salvar_comprovante

    m = db.session.get(Mensalidade, mensalidade_id)
    if not m or m.associado_id != associado.id:
        abort(404)
    if m.status not in ("aberta", "recusada"):
        flash("Esta mensalidade não está aguardando comprovante.", "aviso")
        return redirect(url_for("area.inicio"))
    nome, erro = salvar_comprovante(request.files.get("comprovante"))
    if erro:
        flash(erro, "erro")
        return redirect(url_for("area.inicio"))
    m.comprovante = nome
    m.forma = "pix"
    m.status = "em_analise"
    m.enviado_em = datetime.now()
    m.registrado_por_id = None  # enviado pelo próprio associado
    m.motivo_recusa = None
    db.session.commit()
    flash(f"Comprovante de {m.mes_ano} enviado! A equipe vai conferir e validar.", "ok")
    return redirect(url_for("area.inicio"))
