"""Usuários da equipe: cada pessoa com seu login (o presidente cadastra), e troca da própria senha."""
import os
import secrets
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import db
from .models import Usuario
from .seguranca import limpar

bp = Blueprint("equipe", __name__, url_prefix="/equipe")

from .permissoes import PERFIS
LETRAS = "abcdefghjkmnpqrstuvwxyz23456789"


def presidente_required(view):
    @wraps(view)
    @login_required
    def envolvido(*args, **kwargs):
        if not current_user.presidente:  # (a regra também vale em permissoes.py)
            abort(403)
        return view(*args, **kwargs)

    return envolvido


def senha_provisoria():
    return "".join(secrets.choice(LETRAS) for _ in range(8))


def presidentes_ativos():
    return db.session.execute(
        db.select(db.func.count()).select_from(Usuario).filter_by(perfil="presidente", ativo=True)
    ).scalar()


@bp.route("/")
@presidente_required
def lista():
    usuarios = db.session.execute(db.select(Usuario).order_by(Usuario.ativo.desc(), Usuario.nome)).scalars().all()
    return render_template("equipe/lista.html", usuarios=usuarios, perfis=PERFIS)


@bp.route("/novo", methods=["POST"])
@presidente_required
def novo():
    nome = request.form.get("nome", "").strip()
    login = request.form.get("login", "").strip().lower()
    perfil = request.form.get("perfil", "voluntario")
    perfil = "administracao" if perfil == "equipe" else perfil  # nome antigo
    if not nome or not login or perfil not in PERFIS:
        flash("Preencha o nome e o usuário.", "erro")
    elif not login.replace(".", "").replace("_", "").isalnum() or len(login) > 60:
        flash("O usuário só pode ter letras, números, ponto e sublinhado (ex.: maria.silva).", "erro")
    elif db.session.execute(db.select(Usuario).filter_by(login=login)).scalar_one_or_none():
        flash(f"Já existe o usuário {login}.", "erro")
    else:
        senha = senha_provisoria()
        usuario = Usuario(nome=nome, login=login, perfil=perfil, trocar_senha=True)
        usuario.definir_senha(senha)
        db.session.add(usuario)
        db.session.commit()
        flash(f"{nome} cadastrado(a). Usuário: {login} · Senha provisória: {senha} "
              "(anote e entregue; no primeiro acesso a pessoa cria a própria senha).", "ok")
    return redirect(url_for("equipe.lista"))


@bp.route("/<int:usuario_id>/senha", methods=["POST"])
@presidente_required
def redefinir_senha(usuario_id):
    usuario = db.session.get(Usuario, usuario_id) or abort(404)
    senha = senha_provisoria()
    usuario.definir_senha(senha)
    usuario.trocar_senha = True
    limpar(f"equipe:{usuario.login}")  # desfaz bloqueio por senha errada
    db.session.commit()
    flash(f"Nova senha provisória de {usuario.nome}: {senha}", "ok")
    return redirect(url_for("equipe.lista"))


@bp.route("/<int:usuario_id>/ativo", methods=["POST"])
@presidente_required
def alternar_ativo(usuario_id):
    usuario = db.session.get(Usuario, usuario_id) or abort(404)
    if usuario.id == current_user.id:
        flash("Você não pode desativar o seu próprio acesso.", "erro")
    elif usuario.ativo and usuario.presidente and presidentes_ativos() <= 1:
        flash("É preciso ter pelo menos um presidente ativo.", "erro")
    else:
        usuario.ativo = not usuario.ativo
        db.session.commit()
        flash(f"Acesso de {usuario.nome} {'reativado' if usuario.ativo else 'desativado'}.", "ok")
    return redirect(url_for("equipe.lista"))


@bp.route("/<int:usuario_id>/perfil", methods=["POST"])
@presidente_required
def alterar_perfil(usuario_id):
    usuario = db.session.get(Usuario, usuario_id) or abort(404)
    perfil = request.form.get("perfil")
    perfil = "administracao" if perfil == "equipe" else perfil  # nome antigo
    if perfil not in PERFIS:
        abort(400)
    if usuario.presidente and perfil != "presidente" and presidentes_ativos() <= 1:
        flash("É preciso ter pelo menos um presidente ativo.", "erro")
    else:
        usuario.perfil = perfil
        db.session.commit()
        flash(f"Perfil de {usuario.nome} alterado.", "ok")
    return redirect(url_for("equipe.lista"))


@bp.route("/minha-senha", methods=["GET", "POST"])
@login_required
def minha_senha():
    if request.method == "POST":
        atual = request.form.get("atual", "")
        nova = request.form.get("nova", "")
        if not current_user.conferir_senha(atual):
            flash("A senha atual não confere.", "erro")
        elif len(nova) < 8:
            flash("A senha nova precisa ter pelo menos 8 caracteres.", "erro")
        elif nova != request.form.get("confirmar"):
            flash("As senhas novas não são iguais.", "erro")
        elif nova == atual:
            flash("A senha nova precisa ser diferente da atual.", "erro")
        else:
            current_user.definir_senha(nova)
            current_user.trocar_senha = False
            db.session.commit()
            flash("Senha alterada.", "ok")
            return redirect(url_for("painel.inicio"))
    return render_template("equipe/minha_senha.html")


@bp.route("/backup.zip")
@presidente_required
def baixar_backup():
    """Baixa agora uma cópia de segurança (banco, fotos e comprovantes). Útil quando a hospedagem não agenda tarefas."""
    import tempfile

    from flask import after_this_request, current_app, send_file

    import backup

    pasta = tempfile.mkdtemp()
    antigos = (backup.INSTANCE, backup.PASTA_BACKUP)
    backup.INSTANCE, backup.PASTA_BACKUP = current_app.instance_path, pasta
    try:
        caminho = backup.fazer_backup(manter=1)
    finally:
        backup.INSTANCE, backup.PASTA_BACKUP = antigos

    @after_this_request
    def apagar(resposta):
        import shutil
        shutil.rmtree(pasta, ignore_errors=True)
        return resposta

    return send_file(caminho, as_attachment=True, download_name=os.path.basename(caminho), mimetype="application/zip")
