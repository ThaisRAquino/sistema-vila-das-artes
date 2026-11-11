"""Indicadores de impacto: o "antes" (diagnóstico da 1ª visita) ao lado do "depois" medido pelo sistema."""
from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func

from . import db
from .models import Assembleia, Associado, Aviso, Documento, Mensalidade, Presenca, RegistroExportacao
from .regras import competencia_anterior, competencia_atual

bp = Blueprint("indicadores", __name__, url_prefix="/indicadores")

# Números do diagnóstico (1ª visita técnica, 11/10/2026 – Roteiro da 1ª Visita)
ANTES = {
    "familias": "508 fichas em papel",
    "busca": "15 a 20 min (cronometrado)",
    "lista": "cerca de 1 semana (relato da diretoria)",
    "documentacao": "75% (estimativa da diretoria)",
    "duplicidade": "4 casos de nº de sócio repetido",
    "horas": "cerca de 48 h por semana (relato)",
}


def contar(consulta):
    return db.session.execute(consulta).scalar() or 0


@bp.route("/")
@login_required
def inicio():
    agora = datetime.now()
    ativos = contar(db.select(func.count()).select_from(Associado).filter_by(situacao="ativo"))
    pendentes = contar(
        db.select(func.count(func.distinct(Documento.associado_id))).join(Associado)
        .filter(Documento.status == "pendente", Associado.situacao == "ativo")
    )
    completos = ativos - pendentes
    numeros_repetidos = contar(
        db.select(func.count()).select_from(
            db.select(Associado.numero_socio).group_by(Associado.numero_socio).having(func.count() > 1).subquery()
        )
    )

    mes = competencia_anterior(competencia_atual())  # último mês já vencido
    por_status = dict(db.session.execute(
        db.select(Mensalidade.status, func.count()).join(Associado)
        .filter(Mensalidade.competencia == mes, Associado.situacao == "ativo").group_by(Mensalidade.status)
    ).all())
    cobradas = sum(v for k, v in por_status.items() if k != "isenta")
    pagas = por_status.get("paga", 0)

    validadas = db.session.execute(
        db.select(Mensalidade.enviado_em, Mensalidade.validado_em).filter(
            Mensalidade.enviado_em.is_not(None), Mensalidade.validado_em.is_not(None),
            Mensalidade.validado_em >= agora - timedelta(days=90))
    ).all()
    horas = [(v - e).total_seconds() / 3600 for e, v in validadas if v >= e]
    tempo_validacao = sum(horas) / len(horas) if horas else None

    ultimas = db.session.execute(
        db.select(Assembleia).filter_by(encerrada=True).order_by(Assembleia.data.desc()).limit(3)
    ).scalars().all()
    presencas = [contar(db.select(func.count()).select_from(Presenca).filter_by(assembleia_id=a.id)) for a in ultimas]
    presenca_media = sum(presencas) / len(presencas) if presencas else None

    usando_app = contar(db.select(func.count()).select_from(Associado)
                        .filter(Associado.situacao == "ativo", Associado.termo_aceito_em.is_not(None)))
    com_foto = contar(db.select(func.count()).select_from(Associado)
                      .filter(Associado.situacao == "ativo", Associado.foto.is_not(None)))
    avisos_30 = contar(db.select(func.count()).select_from(Aviso).filter(Aviso.enviado_em >= agora - timedelta(days=30)))
    exportacoes_30 = contar(db.select(func.count()).select_from(RegistroExportacao)
                            .filter(RegistroExportacao.exportado_em >= agora - timedelta(days=30)))

    def pct(parte, todo):
        return round(100 * parte / todo) if todo else 0

    return render_template(
        "indicadores.html", antes=ANTES, ativos=ativos, completos=completos, pct_completos=pct(completos, ativos),
        numeros_repetidos=numeros_repetidos, mes=mes, cobradas=cobradas, pagas=pagas, pct_pagas=pct(pagas, cobradas),
        tempo_validacao=tempo_validacao, ultimas=list(zip(ultimas, presencas)), presenca_media=presenca_media,
        pct_presenca=pct(presenca_media or 0, ativos), usando_app=usando_app, pct_app=pct(usando_app, ativos),
        com_foto=com_foto, avisos_30=avisos_30, exportacoes_30=exportacoes_30, gerado_em=agora,
    )
