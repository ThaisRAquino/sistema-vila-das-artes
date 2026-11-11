"""Acesso dos associados à área do associado: situação de cada um e códigos de primeiro acesso em lote."""
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from . import db
from .area_associado import gerar_codigo_acesso
from .models import Associado

bp = Blueprint("acessos", __name__, url_prefix="/acessos")

ETAPAS = {
    "sem_codigo": "Sem código",
    "codigo_enviado": "Código gerado",
    "codigo_vencido": "Código vencido",
    "senha_criada": "Senha criada",
    "termo_aceito": "Usando a área",
}


def etapa(a, agora):
    if a.senha_hash:
        return "termo_aceito" if a.termo_aceito_em else "senha_criada"
    if a.codigo_acesso:
        return "codigo_enviado" if a.codigo_expira_em and a.codigo_expira_em > agora else "codigo_vencido"
    return "sem_codigo"


@bp.route("/")
@login_required
def lista():
    agora = datetime.now()
    filtro = request.args.get("filtro", "pendentes")
    associados = db.session.execute(
        db.select(Associado).filter_by(situacao="ativo").order_by(Associado.numero_socio)
    ).scalars().all()
    linhas = [(a, etapa(a, agora)) for a in associados]
    contagem = {chave: sum(1 for _, e in linhas if e == chave) for chave in ETAPAS}
    if filtro == "pendentes":
        linhas = [(a, e) for a, e in linhas if e in ("sem_codigo", "codigo_enviado", "codigo_vencido")]
    elif filtro in ETAPAS:
        linhas = [(a, e) for a, e in linhas if e == filtro]
    return render_template("acessos/lista.html", linhas=linhas, contagem=contagem, etapas=ETAPAS,
                           filtro=filtro, total=len(associados))


@bp.route("/gerar", methods=["POST"])
@login_required
def gerar_em_lote():
    """Gera código para quem ainda não tem senha e não tem código válido (não troca códigos já enviados)."""
    agora = datetime.now()
    gerados = 0
    for a in db.session.execute(db.select(Associado).filter_by(situacao="ativo")).scalars():
        if etapa(a, agora) in ("sem_codigo", "codigo_vencido"):
            gerar_codigo_acesso(a)
            gerados += 1
    db.session.commit()
    if gerados:
        flash(f"{gerados} código(s) gerado(s), válidos por 7 dias. Agora envie pelo WhatsApp, um por um.", "ok")
    else:
        flash("Todos os associados já têm senha ou um código válido.", "aviso")
    return redirect(url_for("acessos.lista", filtro="codigo_enviado"))
