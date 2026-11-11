"""Painel inicial da equipe."""
from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func

from . import db
from .models import Assembleia, Associado, Documento, Mensalidade, Presenca
from .regras import associados_em_alerta, competencia_atual, garantir_mensalidades, proxima_assembleia

bp = Blueprint("painel", __name__)


@bp.route("/")
@login_required
def inicio():
    total = db.session.execute(
        db.select(func.count()).select_from(Associado).filter_by(situacao="ativo")
    ).scalar()
    mutirantes = db.session.execute(
        db.select(func.count()).select_from(Associado).filter_by(situacao="ativo", categoria="mutirante")
    ).scalar()

    competencia = competencia_atual()
    garantir_mensalidades(competencia)
    por_status = dict(
        db.session.execute(
            db.select(Mensalidade.status, func.count()).filter_by(competencia=competencia).group_by(Mensalidade.status)
        ).all()
    )
    cobradas = sum(v for k, v in por_status.items() if k != "isenta")
    pagas = por_status.get("paga", 0)
    em_analise = db.session.execute(
        db.select(func.count()).select_from(Mensalidade).filter_by(status="em_analise")
    ).scalar()

    docs_pendentes = db.session.execute(
        db.select(func.count(func.distinct(Documento.associado_id)))
        .join(Associado)
        .filter(Documento.status == "pendente", Associado.situacao == "ativo")
    ).scalar()

    risco, atencao = associados_em_alerta()

    aberta = db.session.execute(
        db.select(Assembleia).filter_by(encerrada=False).order_by(Assembleia.data)
    ).scalars().first()
    ultimas = db.session.execute(
        db.select(Assembleia).filter_by(encerrada=True).order_by(Assembleia.data.desc()).limit(6)
    ).scalars().all()
    presencas = dict(
        db.session.execute(
            db.select(Presenca.assembleia_id, func.count()).group_by(Presenca.assembleia_id)
        ).all()
    )

    return render_template(
        "painel.html",
        total=total,
        regulares=total - mutirantes,
        mutirantes=mutirantes,
        competencia=competencia,
        cobradas=cobradas,
        pagas=pagas,
        em_analise=em_analise,
        docs_pendentes=docs_pendentes,
        risco=risco,
        atencao=atencao,
        aberta=aberta,
        ultimas=list(reversed(ultimas)),
        presencas=presencas,
        maior=max([presencas.get(a.id, 0) for a in ultimas] + [1]),
        proxima=proxima_assembleia(),
    )
