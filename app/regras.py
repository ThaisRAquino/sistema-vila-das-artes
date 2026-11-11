"""Regras da associação: mensalidades do mês, faltas seguidas e alerta de desligamento.

O sistema só ALERTA. A decisão de desligar um associado é sempre da diretoria.
"""
from datetime import date, timedelta
from urllib.parse import quote

from . import db
from .models import (
    VALOR_MENSALIDADE,
    Assembleia,
    Associado,
    Configuracao,
    Mensalidade,
    Presenca,
)
from .utils import somente_digitos

LIMITE_FALTAS = 3
LIMITE_MENSALIDADES = 3
CHAVE_COBRANCA_MUTIRANTES = "cobranca_mutirantes_desde"


# ---------- datas ----------

def competencia_de(dia):
    return f"{dia.year:04d}-{dia.month:02d}"


def competencia_atual():
    return competencia_de(date.today())


def competencia_anterior(competencia, meses=1):
    ano, mes = map(int, competencia.split("-"))
    total = ano * 12 + (mes - 1) - meses
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def segundo_domingo(ano, mes):
    dia = date(ano, mes, 1)
    while dia.weekday() != 6:  # domingo
        dia += timedelta(days=1)
    return dia + timedelta(days=7)


def proxima_assembleia(hoje=None):
    """As assembleias são no 2º domingo de cada mês."""
    hoje = hoje or date.today()
    data = segundo_domingo(hoje.year, hoje.month)
    if data < hoje:
        ano, mes = (hoje.year + 1, 1) if hoje.month == 12 else (hoje.year, hoje.month + 1)
        data = segundo_domingo(ano, mes)
    return data


# ---------- mensalidades ----------

def cobranca_mutirantes_desde():
    return Configuracao.obter(CHAVE_COBRANCA_MUTIRANTES)


def isento_no_mes(associado, competencia):
    """Mutirante é isento até a cobrança ser ativada (novo projeto do CDHU)."""
    if not associado.mutirante:
        return False
    desde = cobranca_mutirantes_desde()
    return not desde or competencia < desde


def garantir_mensalidades(competencia):
    """Cria as mensalidades do mês para todos os associados ativos que ainda não têm."""
    existentes = set(
        db.session.execute(
            db.select(Mensalidade.associado_id).filter_by(competencia=competencia)
        ).scalars()
    )
    ativos = db.session.execute(db.select(Associado).filter_by(situacao="ativo")).scalars()
    for associado in ativos:
        if associado.id in existentes:
            continue
        inscricao = associado.data_inscricao or associado.criado_em.date()
        if competencia < competencia_de(inscricao):
            continue
        status = "isenta" if isento_no_mes(associado, competencia) else "aberta"
        db.session.add(
            Mensalidade(associado=associado, competencia=competencia, valor=VALOR_MENSALIDADE, status=status)
        )
    db.session.commit()


def proximo_recibo(competencia):
    ano = competencia[:4]
    ultimo = db.session.execute(
        db.select(Mensalidade.numero_recibo)
        .filter(Mensalidade.numero_recibo.like(f"{ano}-%"))
        .order_by(Mensalidade.numero_recibo.desc())
    ).scalars().first()
    sequencia = int(ultimo.split("-")[1]) + 1 if ultimo else 1
    return f"{ano}-{sequencia:05d}"


def inicio_da_contagem(associado):
    """A contagem de faltas e mensalidades começa na inscrição ou na última reativação pela diretoria."""
    inicio = associado.data_inscricao or associado.criado_em.date()
    reativacoes = [h.data_decisao for h in associado.historico_situacao if h.situacao == "ativo"]
    return max([inicio] + reativacoes)


def mensalidades_em_aberto_seguidas(associado, ate=None):
    """Conta meses seguidos sem pagamento, do mês vencido mais recente para trás.

    O mês atual ainda não venceu, por isso a contagem começa no mês anterior.
    'Em análise' não conta como atraso: o associado já enviou o comprovante.
    """
    ate = ate or competencia_anterior(competencia_atual())
    por_mes = {m.competencia: m.status for m in associado.mensalidades}
    desde = competencia_de(inicio_da_contagem(associado))
    contagem, mes = 0, ate
    while mes >= desde and por_mes.get(mes) in ("aberta", "recusada"):
        contagem += 1
        mes = competencia_anterior(mes)
    return contagem


# ---------- assembleias ----------

def faltas_seguidas(associado):
    """Conta as assembleias encerradas mais recentes, seguidas, em que o associado faltou."""
    inicio = inicio_da_contagem(associado)
    assembleias = db.session.execute(
        db.select(Assembleia)
        .filter(Assembleia.encerrada.is_(True), Assembleia.data >= inicio)
        .order_by(Assembleia.data.desc())
    ).scalars()
    presentes = set(
        db.session.execute(
            db.select(Presenca.assembleia_id).filter_by(associado_id=associado.id)
        ).scalars()
    )
    contagem = 0
    for assembleia in assembleias:
        if assembleia.id in presentes:
            break
        contagem += 1
    return contagem


def buscar_por_codigo(codigo):
    """Aceita o nº de sócio (ex.: 142 ou 0142) ou o código do QR (ex.: VDA-1A2B3C4D)."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return None, None
    if codigo.startswith("VDA-"):
        associado = db.session.execute(db.select(Associado).filter_by(qr_codigo=codigo)).scalar_one_or_none()
        return associado, "qr"
    digitos = somente_digitos(codigo)
    if not digitos:
        return None, None
    associado = db.session.execute(
        db.select(Associado).filter_by(numero_socio=digitos.zfill(4))
    ).scalar_one_or_none()
    return associado, "numero"


# ---------- situação e alertas ----------

def situacao(associado):
    """Resumo usado no painel, na lista e na ficha."""
    faltas = faltas_seguidas(associado)
    atrasadas = 0 if associado.mutirante and isento_no_mes(associado, competencia_atual()) else mensalidades_em_aberto_seguidas(associado)
    if faltas >= LIMITE_FALTAS or atrasadas >= LIMITE_MENSALIDADES:
        nivel = "risco"
    elif faltas == LIMITE_FALTAS - 1 or atrasadas == LIMITE_MENSALIDADES - 1:
        nivel = "atencao"
    else:
        nivel = "ok"
    motivos = []
    if faltas:
        motivos.append(f"{faltas} falta{'s' if faltas > 1 else ''} seguida{'s' if faltas > 1 else ''}")
    if atrasadas:
        motivos.append(f"{atrasadas} mensalidade{'s' if atrasadas > 1 else ''} em aberto")
    return {"nivel": nivel, "faltas": faltas, "atrasadas": atrasadas, "motivos": motivos}


def associados_em_alerta():
    ativos = db.session.execute(
        db.select(Associado).filter_by(situacao="ativo").order_by(Associado.numero_socio)
    ).scalars().all()
    risco, atencao = [], []
    for associado in ativos:
        s = situacao(associado)
        if s["nivel"] == "risco":
            risco.append((associado, s))
        elif s["nivel"] == "atencao":
            atencao.append((associado, s))
    return risco, atencao


# ---------- mensagens de WhatsApp ----------

def mensagem_whatsapp(associado, motivo):
    from . import contato

    primeiro = associado.nome.split()[0]
    proxima = proxima_assembleia().strftime("%d/%m")
    s = situacao(associado)
    textos = {
        "falta": (
            f"Olá, {primeiro}! Aqui é da Associação Vila das Artes. Você está com {s['faltas']} falta(s) seguida(s) "
            f"nas assembleias. A próxima é no domingo, {proxima}. Contamos com a sua presença! Sócio nº {associado.numero_socio}."
        ),
        "mensalidade": (
            f"Olá, {primeiro}! Aqui é da Associação Vila das Artes. Identificamos {s['atrasadas']} mensalidade(s) em aberto. "
            f"Envie o comprovante pelo sistema ou traga na sede para a equipe conferir. Sócio nº {associado.numero_socio}. "
            f"Dúvidas: WhatsApp {contato.WHATSAPP}."
        ),
        "documento": (
            f"Olá, {primeiro}! Aqui é da Associação Vila das Artes. Falta entregar documento(s) no seu cadastro: "
            + ", ".join(d.tipo for d in associado.documentos if d.status == "pendente")
            + f". Traga na sede {contato.HORARIO_SEDE}. Sócio nº {associado.numero_socio}."
        ),
        "assembleia": (
            f"Olá, {primeiro}! Lembrete da Associação Vila das Artes: a próxima assembleia é no domingo, {proxima}. "
            "Leve sua carteirinha com QR para marcar presença mais rápido."
        ),
    }
    if motivo == "acesso" and associado.codigo_acesso:
        from flask import url_for

        link = url_for("area.primeiro_acesso", _external=True)
        textos["acesso"] = (
            f"Olá, {primeiro}! A Associação Vila das Artes agora tem a área do associado. Acesse {link}, "
            f"digite seu CPF e o código {associado.codigo_acesso} (vale por 7 dias) e crie sua senha. "
            "Lá você vê sua carteirinha, mensalidades e presenças, e pode enviar sua foto. "
            f"Dúvidas: WhatsApp {contato.WHATSAPP}."
        )
    return textos.get(motivo, textos["assembleia"])


def link_whatsapp(celular, mensagem):
    numero = somente_digitos(celular)
    if not numero:
        return None
    if not numero.startswith("55"):
        numero = "55" + numero
    return f"https://wa.me/{numero}?text={quote(mensagem)}"
