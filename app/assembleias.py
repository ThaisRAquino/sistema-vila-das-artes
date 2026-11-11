"""Assembleias: presença pelo nº de sócio ou pelo QR da carteirinha."""

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from . import db
from .models import Assembleia, Associado, Presenca
from .regras import LIMITE_FALTAS, buscar_por_codigo, faltas_seguidas, proxima_assembleia
from .utils import ler_data

bp = Blueprint("assembleias", __name__, url_prefix="/assembleias")


def buscar(assembleia_id):
    a = db.session.get(Assembleia, assembleia_id)
    if not a:
        abort(404)
    return a


@bp.route("/")
@login_required
def lista():
    assembleias = db.session.execute(db.select(Assembleia).order_by(Assembleia.data.desc())).scalars().all()
    totais = dict(
        db.session.execute(
            db.select(Presenca.assembleia_id, func.count()).group_by(Presenca.assembleia_id)
        ).all()
    )
    ativos = db.session.execute(
        db.select(func.count()).select_from(Associado).filter_by(situacao="ativo")
    ).scalar()
    return render_template(
        "assembleias/lista.html",
        assembleias=assembleias,
        totais=totais,
        ativos=ativos,
        sugestao=proxima_assembleia(),
    )


@bp.route("/nova", methods=["POST"])
@login_required
def nova():
    try:
        data = ler_data(request.form.get("data")) or proxima_assembleia()
    except ValueError as erro:
        flash(str(erro), "erro")
        return redirect(url_for("assembleias.lista"))
    existente = db.session.execute(db.select(Assembleia).filter_by(data=data)).scalar_one_or_none()
    if existente:
        flash("Já existe uma assembleia nesta data.", "aviso")
        return redirect(url_for("assembleias.presenca", assembleia_id=existente.id))
    assembleia = Assembleia(data=data)
    db.session.add(assembleia)
    db.session.commit()
    flash(f"Assembleia de {data.strftime('%d/%m/%Y')} criada. A lista de presença está aberta.", "ok")
    return redirect(url_for("assembleias.presenca", assembleia_id=assembleia.id))


def registrar(assembleia, codigo):
    """Marca a presença e devolve (ok, mensagem, associado)."""
    if assembleia.encerrada:
        return False, "A lista desta assembleia já foi encerrada.", None
    associado, forma = buscar_por_codigo(codigo)
    if not associado:
        return False, f"Nº ou QR “{codigo}” não encontrado.", None
    if associado.situacao != "ativo":
        return False, f"{associado.nome} não está ativo.", associado
    ja = db.session.execute(
        db.select(Presenca).filter_by(assembleia_id=assembleia.id, associado_id=associado.id)
    ).scalar_one_or_none()
    if ja:
        return False, f"{associado.numero_socio} · {associado.nome} já estava presente (às {ja.registrada_em:%H:%M}).", associado
    db.session.add(
        Presenca(assembleia=assembleia, associado=associado, forma=forma, registrado_por_id=current_user.id)
    )
    db.session.commit()
    return True, f"Presença marcada: {associado.numero_socio} · {associado.nome}", associado


@bp.route("/<int:assembleia_id>", methods=["GET", "POST"])
@login_required
def presenca(assembleia_id):
    assembleia = buscar(assembleia_id)
    if request.method == "POST":
        ok, mensagem, associado = registrar(assembleia, request.form.get("codigo"))
        if request.headers.get("X-Requested-With") == "fetch":
            receber_url = None
            if associado and associado.situacao == "ativo":
                receber_url = url_for("mensalidades.receber", codigo=associado.numero_socio, voltar=assembleia.id)
            return jsonify(ok=ok, mensagem=mensagem, receber_url=receber_url)
        flash(mensagem, "ok" if ok else "erro")
        return redirect(url_for("assembleias.presenca", assembleia_id=assembleia.id))

    recentes = db.session.execute(
        db.select(Presenca).filter_by(assembleia_id=assembleia.id).order_by(Presenca.registrada_em.desc()).limit(12)
    ).scalars().all()
    total = db.session.execute(
        db.select(func.count()).select_from(Presenca).filter_by(assembleia_id=assembleia.id)
    ).scalar()
    ativos = db.session.execute(
        db.select(func.count()).select_from(Associado).filter_by(situacao="ativo")
    ).scalar()

    previa = None
    if not assembleia.encerrada:
        # Quantos chegariam a 3 faltas se a lista fosse encerrada agora
        presentes = {p.associado_id for p in assembleia.presencas}
        chegam_ao_limite = 0
        for associado in db.session.execute(db.select(Associado).filter_by(situacao="ativo")).scalars():
            inscricao = associado.data_inscricao or associado.criado_em.date()
            if associado.id not in presentes and inscricao <= assembleia.data:
                if faltas_seguidas(associado) + 1 >= LIMITE_FALTAS:
                    chegam_ao_limite += 1
        previa = chegam_ao_limite
    return render_template(
        "assembleias/presenca.html",
        assembleia=assembleia,
        recentes=recentes,
        total=total,
        ativos=ativos,
        previa=previa,
    )


@bp.route("/<int:assembleia_id>/encerrar", methods=["POST"])
@login_required
def encerrar(assembleia_id):
    assembleia = buscar(assembleia_id)
    assembleia.encerrada = True
    db.session.commit()
    flash("Lista de presença encerrada. Confira no painel quem chegou ao limite de faltas.", "ok")
    return redirect(url_for("painel.inicio"))


@bp.route("/<int:assembleia_id>/reabrir", methods=["POST"])
@login_required
def reabrir(assembleia_id):
    assembleia = buscar(assembleia_id)
    assembleia.encerrada = False
    db.session.commit()
    flash("Lista de presença reaberta.", "aviso")
    return redirect(url_for("assembleias.presenca", assembleia_id=assembleia.id))


@bp.route("/<int:assembleia_id>/presencas/<int:presenca_id>/remover", methods=["POST"])
@login_required
def remover_presenca(assembleia_id, presenca_id):
    p = db.session.get(Presenca, presenca_id)
    if not p or p.assembleia_id != assembleia_id or p.assembleia.encerrada:
        abort(404)
    db.session.delete(p)
    db.session.commit()
    flash("Presença removida.", "aviso")
    return redirect(url_for("assembleias.presenca", assembleia_id=assembleia_id))
