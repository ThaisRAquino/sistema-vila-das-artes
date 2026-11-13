"""Sistema Vila das Artes - gestão de associados.

Projeto de Extensão UniFECAF (ADS) para a Associação Vila das Artes, Embu das Artes/SP.
"""
import os
import secrets
from datetime import timedelta

from flask import Flask, abort, request, session
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Entre com seu usuário para continuar."
login_manager.login_message_category = "aviso"


def _secret_key(instance_path):
    """Usa SECRET_KEY do ambiente ou cria uma chave aleatória guardada na pasta instance."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    os.makedirs(instance_path, exist_ok=True)
    caminho = os.path.join(instance_path, "secret_key")
    if not os.path.exists(caminho):
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    with open(caminho, encoding="utf-8") as f:
        return f.read().strip()


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        SECRET_KEY=_secret_key(app.instance_path),
        SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(app.instance_path, "vila_das_artes.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        WTF_CSRF_ENABLED=True,
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,  # fotos de celular de até 20 MB (o sistema reduz ao salvar)
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),  # login vale no máximo 8 horas
    )
    if config:
        app.config.update(config)
    if _producao():
        _configurar_producao(app)

    db.init_app(app)
    login_manager.init_app(app)

    from . import models  # noqa: F401  (registra as tabelas)
    from .auth import bp as auth_bp
    from .painel import bp as painel_bp
    from .associados import bp as associados_bp
    from .mensalidades import bp as mensalidades_bp
    from .assembleias import bp as assembleias_bp
    from .avisos import bp as avisos_bp
    from .area_associado import bp as area_bp
    from .equipe import bp as equipe_bp
    from .importacao import bp as importacao_bp
    from .acessos import bp as acessos_bp
    from .indicadores import bp as indicadores_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(painel_bp)
    app.register_blueprint(associados_bp)
    app.register_blueprint(mensalidades_bp)
    app.register_blueprint(assembleias_bp)
    app.register_blueprint(avisos_bp)
    app.register_blueprint(area_bp)
    app.register_blueprint(equipe_bp)
    app.register_blueprint(importacao_bp)
    app.register_blueprint(acessos_bp)
    app.register_blueprint(indicadores_bp)

    from .permissoes import conferir_permissao, pode

    app.before_request(conferir_permissao)
    app.jinja_env.globals["pode"] = pode
    from . import contato

    app.jinja_env.globals["contato"] = contato

    @app.before_request
    def exigir_troca_de_senha():
        """Quem entrou com senha provisória só usa o sistema depois de criar a própria senha."""
        from flask import redirect, url_for
        from flask_login import current_user

        if (current_user.is_authenticated and current_user.trocar_senha
                and request.endpoint not in ("equipe.minha_senha", "auth.sair", "static", "service_worker")):
            return redirect(url_for("equipe.minha_senha"))

    @app.route("/sw.js")
    def service_worker():
        """O service worker fica na raiz para valer para o site todo (app instalável)."""
        from flask import send_from_directory
        resposta = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta

    @app.after_request
    def cabecalhos_de_seguranca(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Referrer-Policy", "same-origin")
        resposta.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if app.config.get("SESSION_COOKIE_SECURE"):
            resposta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return resposta

    def pagina_de_erro(codigo, titulo, texto):
        from flask import render_template
        return render_template("erro.html", codigo=codigo, titulo=titulo, texto=texto), codigo

    app.register_error_handler(400, lambda e: pagina_de_erro(400, "Não deu certo", getattr(e, "description", "") or "Recarregue a página e tente de novo."))
    app.register_error_handler(403, lambda e: pagina_de_erro(403, "Sem permissão", "Esta ação é de outro perfil da equipe. Peça para a administração ou para o presidente."))
    app.register_error_handler(404, lambda e: pagina_de_erro(404, "Página não encontrada", "O endereço pode estar errado ou o item foi removido."))
    app.register_error_handler(500, lambda e: pagina_de_erro(500, "Erro no sistema", "Algo deu errado do nosso lado. Tente de novo; se continuar, avise a equipe de tecnologia."))

    @app.errorhandler(413)
    def arquivo_grande(_erro):
        from flask import flash, redirect, request as req
        flash("Arquivo muito grande. Envie uma foto ou PDF de até 20 MB.", "erro")
        return redirect(req.referrer or "/")

    _configurar_csrf(app)
    _registrar_filtros(app)

    with app.app_context():
        db.create_all()
        _atualizar_banco()

    return app


def _producao():
    return os.environ.get("VDA_PRODUCAO", "").lower() in ("1", "sim", "true")


def _configurar_producao(app):
    """Ajustes para o sistema publicado na internet (com https).

    Ative com a variável de ambiente VDA_PRODUCAO=1 no serviço de hospedagem.
    """
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.config.update(
        SESSION_COOKIE_SECURE=True,      # cookie de login só trafega por https
        PREFERRED_URL_SCHEME="https",    # links das mensagens de WhatsApp saem com https
        DEBUG=False,
    )
    # a hospedagem fica na frente do sistema (proxy): isto faz o Flask enxergar o https e o domínio certos
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def _atualizar_banco():
    """Acrescenta no banco as colunas novas das atualizações do sistema, sem apagar nenhum dado.

    Assim, ao atualizar o sistema, não é preciso apagar o arquivo do banco.
    """
    from sqlalchemy import inspect, text

    inspetor = inspect(db.engine)
    tabelas = set(inspetor.get_table_names())
    with db.engine.begin() as conexao:
        if "usuarios" in tabelas:  # perfil antigo "equipe" virou "administracao"
            conexao.execute(text("UPDATE usuarios SET perfil = 'administracao' WHERE perfil = 'equipe'"))
        for tabela in db.metadata.sorted_tables:
            if tabela.name not in tabelas:
                continue
            existentes = {c["name"] for c in inspetor.get_columns(tabela.name)}
            for coluna in tabela.columns:
                if coluna.name not in existentes:
                    tipo = coluna.type.compile(dialect=db.engine.dialect)
                    conexao.execute(text(f'ALTER TABLE "{tabela.name}" ADD COLUMN "{coluna.name}" {tipo}'))


def _configurar_csrf(app):
    """Proteção simples contra CSRF: todo formulário POST precisa do token da sessão."""

    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def verificar_csrf():
        if not app.config.get("WTF_CSRF_ENABLED"):
            return
        if request.method == "POST":
            enviado = request.form.get("_csrf")
            esperado = session.get("_csrf")
            if not enviado or not esperado or not secrets.compare_digest(enviado, esperado):
                abort(400, "Formulário expirado. Recarregue a página e tente de novo.")


def _registrar_filtros(app):
    from .utils import formatar_cep, formatar_cpf, mascarar_cpf, formatar_data, formatar_moeda

    app.jinja_env.filters["cpf"] = formatar_cpf
    app.jinja_env.filters["cep"] = formatar_cep
    app.jinja_env.filters["cpf_mascarado"] = mascarar_cpf
    app.jinja_env.filters["data"] = formatar_data
    app.jinja_env.filters["moeda"] = formatar_moeda

    from .regras import situacao, link_whatsapp

    app.jinja_env.globals["situacao"] = situacao
    app.jinja_env.globals["tem_whatsapp"] = lambda a: bool(link_whatsapp(a.celular, "x"))
