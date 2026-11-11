"""Bloqueio de tentativas de acesso, guardado no banco (vale para equipe e associados).

Guardar no banco (e não só no navegador) impede que alguém fuja do bloqueio apagando os cookies.
"""
from datetime import datetime, timedelta

from . import db
from .models import TentativaAcesso

MAX_FALHAS = 5
TEMPO_BLOQUEIO = timedelta(minutes=15)


def bloqueado(chave):
    t = db.session.get(TentativaAcesso, chave)
    return bool(t and t.bloqueado_ate and t.bloqueado_ate > datetime.now())


def registrar_falha(chave):
    t = db.session.get(TentativaAcesso, chave) or TentativaAcesso(chave=chave, falhas=0)
    if t.bloqueado_ate and t.bloqueado_ate <= datetime.now():
        t.falhas, t.bloqueado_ate = 0, None  # o bloqueio anterior já venceu
    t.falhas = (t.falhas or 0) + 1
    if t.falhas >= MAX_FALHAS:
        t.bloqueado_ate = datetime.now() + TEMPO_BLOQUEIO
    db.session.add(t)
    db.session.commit()


def limpar(chave):
    t = db.session.get(TentativaAcesso, chave)
    if t:
        db.session.delete(t)
        db.session.commit()
