"""Login e logout da equipe."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from datetime import datetime

from . import db
from .models import Usuario
from .seguranca import bloqueado, limpar, registrar_falha

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("painel.inicio"))
    if request.method == "POST":
        login_digitado = request.form.get("login", "").strip().lower()
        senha = request.form.get("senha", "")
        chave = f"equipe:{login_digitado[:60]}"
        if bloqueado(chave):
            flash("Muitas tentativas com senha errada. Aguarde 15 minutos ou peça para o presidente redefinir sua senha.", "erro")
            return render_template("login.html")
        usuario = db.session.execute(
            db.select(Usuario).filter_by(login=login_digitado)
        ).scalar_one_or_none()
        if usuario and usuario.ativo and usuario.conferir_senha(senha):
            limpar(chave)
            usuario.ultimo_acesso_em = datetime.now()
            db.session.commit()
            session.permanent = True  # expira em 8 horas (PERMANENT_SESSION_LIFETIME)
            login_user(usuario)
            if usuario.trocar_senha:
                flash("Sua senha é provisória. Crie uma senha sua para continuar.", "aviso")
                return redirect(url_for("equipe.minha_senha"))
            destino = request.args.get("next")
            if not destino or not destino.startswith("/") or destino.startswith("//"):
                destino = url_for("painel.inicio")
            return redirect(destino)
        registrar_falha(chave)
        flash("Usuário ou senha incorretos.", "erro")
    return render_template("login.html")


@bp.route("/sair", methods=["POST"])
@login_required
def sair():
    logout_user()
    flash("Você saiu do sistema.", "ok")
    return redirect(url_for("auth.login"))
