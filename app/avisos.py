"""Avisos pelo WhatsApp: o sistema prepara a mensagem e a equipe só toca para enviar."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import db
from .models import Associado, Aviso
from .regras import link_whatsapp, mensagem_whatsapp

bp = Blueprint("avisos", __name__, url_prefix="/avisos")

MOTIVOS = ("falta", "mensalidade", "documento", "assembleia", "acesso")


@bp.route("/")
@login_required
def lista():
    avisos = db.session.execute(db.select(Aviso).order_by(Aviso.enviado_em.desc()).limit(100)).scalars().all()
    return render_template("avisos/lista.html", avisos=avisos)


@bp.route("/<int:associado_id>/whatsapp", methods=["POST"])
@login_required
def whatsapp(associado_id):
    """Registra o aviso no histórico e abre o WhatsApp com a mensagem pronta."""
    associado = db.session.get(Associado, associado_id)
    if not associado:
        abort(404)
    motivo = request.form.get("motivo")
    if motivo not in MOTIVOS:
        motivo = "assembleia"
    mensagem = mensagem_whatsapp(associado, motivo)
    link = link_whatsapp(associado.celular, mensagem)
    if not link:
        flash(f"{associado.nome} não tem celular cadastrado. Atualize a ficha.", "erro")
        return redirect(url_for("associados.ficha", associado_id=associado.id))
    db.session.add(Aviso(associado=associado, motivo=motivo, mensagem=mensagem, enviado_por_id=current_user.id))
    db.session.commit()
    return redirect(link)
