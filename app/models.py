"""Tabelas do banco, conforme o modelo de dados do projeto (a partir da ficha de inscrição)."""
import secrets
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, login_manager

CATEGORIAS = ("regular", "mutirante")
SITUACOES = ("ativo", "desligado")
TIPOS_DOCUMENTO = (
    "RG",
    "CPF",
    "Título de eleitor",
    "Comprovante de endereço",
    "Carteira de trabalho",
)
ESTADOS_CIVIS = ("casado", "solteiro", "divorciado", "viúvo", "separado", "outro")
TIPOS_RESIDENCIA = ("alugada", "própria", "cedida", "mora com os pais", "área da prefeitura", "outra")
STATUS_MENSALIDADE = ("aberta", "em_analise", "paga", "recusada", "isenta")
VALOR_MENSALIDADE = 50.0
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def agora():
    return datetime.now()


def novo_codigo_qr():
    """Código secreto e único usado no QR da carteirinha (não usa CPF nem nº de sócio)."""
    return "VDA-" + secrets.token_hex(4).upper()


class Carimbo:
    criado_em = db.Column(db.DateTime, default=agora, nullable=False)
    atualizado_em = db.Column(db.DateTime, default=agora, onupdate=agora, nullable=False)


class Usuario(UserMixin, Carimbo, db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    login = db.Column(db.String(60), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(20), nullable=False, default="administracao")  # presidente | administracao | voluntario
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    trocar_senha = db.Column(db.Boolean, default=False)  # senha provisória: troca no próximo acesso
    ultimo_acesso_em = db.Column(db.DateTime)

    @property
    def presidente(self):
        return self.perfil == "presidente"

    @property
    def nome_perfil(self):
        from .permissoes import PERFIS, papel
        return PERFIS.get(papel(self), self.perfil)

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def conferir_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_active(self):
        return self.ativo


@login_manager.user_loader
def carregar_usuario(user_id):
    return db.session.get(Usuario, int(user_id))


class Associado(Carimbo, db.Model):
    __tablename__ = "associados"
    id = db.Column(db.Integer, primary_key=True)

    # Controle interno
    numero_socio = db.Column(db.String(10), unique=True, nullable=False, index=True)
    qr_codigo = db.Column(db.String(20), unique=True, nullable=False, default=novo_codigo_qr)
    # "Grupo" na ficha de papel = categoria: regular ou mutirante
    categoria = db.Column(db.String(20), nullable=False, default="regular")
    data_inscricao = db.Column(db.Date)
    situacao = db.Column(db.String(20), nullable=False, default="ativo")
    consentimento_lgpd_em = db.Column(db.DateTime)

    # Área do associado (acesso pelo celular)
    senha_hash = db.Column(db.String(255))
    codigo_acesso = db.Column(db.String(12))
    codigo_expira_em = db.Column(db.DateTime)
    termo_aceito_em = db.Column(db.DateTime)
    termo_versao = db.Column(db.String(10))
    imagem_autorizada_em = db.Column(db.DateTime)  # autorização separada para a foto
    foto = db.Column(db.String(64))  # nome do arquivo na pasta instance/fotos
    foto_enviada_em = db.Column(db.DateTime)

    # Titular
    nome = db.Column(db.String(150), nullable=False)
    cpf = db.Column(db.String(11), unique=True, nullable=False, index=True)
    rg = db.Column(db.String(20))
    orgao_emissor = db.Column(db.String(20))
    uf_rg = db.Column(db.String(2))
    data_emissao_rg = db.Column(db.Date)
    data_nascimento = db.Column(db.Date)
    nacionalidade = db.Column(db.String(40))
    naturalidade = db.Column(db.String(80))
    nome_pai = db.Column(db.String(150))
    nome_mae = db.Column(db.String(150))
    estado_civil = db.Column(db.String(20))
    grau_instrucao = db.Column(db.String(60))
    profissao = db.Column(db.String(80))
    renda = db.Column(db.Float)
    empresa = db.Column(db.String(120))
    cnpj = db.Column(db.String(14))
    data_admissao = db.Column(db.Date)
    ctps = db.Column(db.String(20))
    serie_ctps = db.Column(db.String(10))
    titulo_eleitor = db.Column(db.String(20))

    # Contato
    celular = db.Column(db.String(20))
    tel_residencial = db.Column(db.String(20))
    recado = db.Column(db.String(60))
    email = db.Column(db.String(120))

    # Endereço e moradia
    rua = db.Column(db.String(150))
    numero = db.Column(db.String(10))
    bairro = db.Column(db.String(80))
    cidade = db.Column(db.String(80), default="Embu das Artes")
    uf = db.Column(db.String(2), default="SP")
    cep = db.Column(db.String(8))
    tipo_residencia = db.Column(db.String(30))
    valor_aluguel = db.Column(db.Float)
    renda_familiar_total = db.Column(db.Float)

    familiares = db.relationship("Familiar", backref="associado", cascade="all, delete-orphan")
    documentos = db.relationship(
        "Documento", backref="associado", cascade="all, delete-orphan", order_by="Documento.id"
    )
    mensalidades = db.relationship(
        "Mensalidade", backref="associado", cascade="all, delete-orphan", order_by="Mensalidade.competencia.desc()"
    )
    presencas = db.relationship("Presenca", backref="associado", cascade="all, delete-orphan")
    avisos = db.relationship(
        "Aviso", backref="associado", cascade="all, delete-orphan", order_by="Aviso.enviado_em.desc()"
    )
    historico_situacao = db.relationship(
        "HistoricoSituacao",
        backref="associado",
        cascade="all, delete-orphan",
        order_by="HistoricoSituacao.registrado_em.desc()",
    )
    historico_numero = db.relationship(
        "HistoricoNumeroSocio",
        backref="associado",
        cascade="all, delete-orphan",
        order_by="HistoricoNumeroSocio.alterado_em.desc()",
    )

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def conferir_senha(self, senha):
        return bool(self.senha_hash) and check_password_hash(self.senha_hash, senha)

    @property
    def tem_acesso(self):
        return bool(self.senha_hash)

    @property
    def mutirante(self):
        return self.categoria == "mutirante"

    @property
    def docs_entregues(self):
        return sum(1 for d in self.documentos if d.status == "entregue")

    @property
    def docs_total(self):
        return len(self.documentos)

    @property
    def iniciais(self):
        partes = [p for p in self.nome.split() if len(p) > 2]
        return "".join(p[0] for p in partes[:2]).upper() or self.nome[:2].upper()

    def criar_checklist(self):
        for tipo in TIPOS_DOCUMENTO:
            self.documentos.append(Documento(tipo=tipo, status="pendente"))


class HistoricoNumeroSocio(db.Model):
    """Registra quem alterou o nº de sócio e quando."""

    __tablename__ = "historico_numero_socio"
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey("associados.id"), nullable=False)
    numero_anterior = db.Column(db.String(10), nullable=False)
    numero_novo = db.Column(db.String(10), nullable=False)
    motivo = db.Column(db.String(200))
    alterado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    alterado_por = db.relationship("Usuario")
    alterado_em = db.Column(db.DateTime, default=agora, nullable=False)


MOTIVOS_DESLIGAMENTO = (
    "3 faltas seguidas nas assembleias",
    "3 mensalidades seguidas em aberto",
    "A pedido do associado",
    "Falecimento",
    "Outro motivo",
)


class HistoricoSituacao(db.Model):
    """Decisões da diretoria: desligamento e reativação, com motivo, data e quem registrou."""

    __tablename__ = "historico_situacao"
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey("associados.id"), nullable=False)
    situacao = db.Column(db.String(20), nullable=False)  # desligado | ativo (reativado)
    motivo = db.Column(db.String(120), nullable=False)
    observacao = db.Column(db.String(300))
    data_decisao = db.Column(db.Date, nullable=False)
    registrado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    registrado_por = db.relationship("Usuario")
    registrado_em = db.Column(db.DateTime, default=agora, nullable=False)


class RegistroExportacao(db.Model):
    """LGPD: guarda quem exportou listas com dados pessoais, quando e quantos associados."""

    __tablename__ = "registro_exportacao"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    usuario = db.relationship("Usuario")
    filtros = db.Column(db.String(200))
    quantidade = db.Column(db.Integer, nullable=False, default=0)
    exportado_em = db.Column(db.DateTime, default=agora, nullable=False)


class Familiar(Carimbo, db.Model):
    __tablename__ = "familiares"
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey("associados.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # cônjuge | dependente
    nome = db.Column(db.String(150), nullable=False)
    cpf = db.Column(db.String(11))
    rg = db.Column(db.String(20))
    data_nascimento = db.Column(db.Date)
    estado_civil = db.Column(db.String(20))
    profissao = db.Column(db.String(80))
    renda = db.Column(db.Float)
    trabalha = db.Column(db.Boolean)


class Documento(Carimbo, db.Model):
    __tablename__ = "documentos"
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey("associados.id"), nullable=False)
    tipo = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pendente")  # entregue | pendente
    arquivo = db.Column(db.String(255))
    validade = db.Column(db.Date)
    conferido_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    conferido_por = db.relationship("Usuario")
    conferido_em = db.Column(db.DateTime)


class Mensalidade(Carimbo, db.Model):
    """Só fica 'paga' depois que a equipe valida o comprovante (2º bloco do desenvolvimento)."""

    __tablename__ = "mensalidades"
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey("associados.id"), nullable=False)
    competencia = db.Column(db.String(7), nullable=False)  # aaaa-mm
    valor = db.Column(db.Float, nullable=False, default=50.0)
    forma = db.Column(db.String(20))  # pix | dinheiro
    status = db.Column(db.String(20), nullable=False, default="aberta")
    comprovante = db.Column(db.String(255))
    enviado_em = db.Column(db.DateTime)
    validado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    validado_em = db.Column(db.DateTime)
    motivo_recusa = db.Column(db.String(200))
    numero_recibo = db.Column(db.String(20), unique=True)
    registrado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    validado_por = db.relationship("Usuario", foreign_keys=[validado_por_id])
    registrado_por = db.relationship("Usuario", foreign_keys=[registrado_por_id])
    __table_args__ = (db.UniqueConstraint("associado_id", "competencia", name="uq_mensalidade_mes"),)

    @property
    def mes_ano(self):
        ano, mes = self.competencia.split("-")
        return f"{MESES[int(mes) - 1]}/{ano}"


class Assembleia(Carimbo, db.Model):
    __tablename__ = "assembleias"
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, unique=True)
    local = db.Column(db.String(120), default="Sede – Rua Juquitiba, 92")
    encerrada = db.Column(db.Boolean, nullable=False, default=False)
    presencas = db.relationship("Presenca", backref="assembleia", cascade="all, delete-orphan")


class Presenca(db.Model):
    __tablename__ = "presencas"
    id = db.Column(db.Integer, primary_key=True)
    assembleia_id = db.Column(db.Integer, db.ForeignKey("assembleias.id"), nullable=False)
    associado_id = db.Column(db.Integer, db.ForeignKey("associados.id"), nullable=False)
    registrada_em = db.Column(db.DateTime, default=agora, nullable=False)
    forma = db.Column(db.String(10), default="numero")  # numero | qr
    registrado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    __table_args__ = (db.UniqueConstraint("assembleia_id", "associado_id", name="uq_presenca"),)


class Aviso(db.Model):
    __tablename__ = "avisos"
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey("associados.id"), nullable=False)
    motivo = db.Column(db.String(20), nullable=False)  # mensalidade | falta | documento | assembleia | acesso
    mensagem = db.Column(db.Text, nullable=False)
    enviado_em = db.Column(db.DateTime, default=agora)
    enviado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    enviado_por = db.relationship("Usuario")


class Configuracao(db.Model):
    """Ajustes gerais (ex.: mês em que a cobrança dos mutirantes foi ativada)."""

    __tablename__ = "configuracoes"
    chave = db.Column(db.String(60), primary_key=True)
    valor = db.Column(db.String(200))

    @staticmethod
    def obter(chave, padrao=None):
        item = db.session.get(Configuracao, chave)
        return item.valor if item and item.valor else padrao

    @staticmethod
    def definir(chave, valor):
        item = db.session.get(Configuracao, chave) or Configuracao(chave=chave)
        item.valor = valor
        db.session.add(item)


class TentativaAcesso(db.Model):
    """Conta senhas erradas por usuário/CPF. Depois de 5 erros, bloqueia por 15 minutos."""

    __tablename__ = "tentativas_acesso"
    chave = db.Column(db.String(80), primary_key=True)  # ex.: equipe:admin | associado:52998224725
    falhas = db.Column(db.Integer, nullable=False, default=0)
    bloqueado_ate = db.Column(db.DateTime)
    atualizado_em = db.Column(db.DateTime, default=agora, onupdate=agora)
