"""O que cada perfil da equipe pode fazer, conforme a organização da associação.

- Presidente (diretoria): tudo, cadastra a equipe e registra as decisões da diretoria.
- Administração: faz a conferência (valida comprovantes, mantém o cadastro, importa e exporta listas).
- Voluntário: nas assembleias, marca presença e recebe pagamentos e comprovantes (que a administração confere).
"""
from flask import abort, request
from flask_login import current_user

PERFIS = {
    "presidente": "Presidente / Diretoria",
    "administracao": "Administração (conferência)",
    "voluntario": "Voluntário (presença e coleta)",
}

# Ações só da conferência (presidente e administração)
CONFERENCIA = {
    "associados.exportar", "associados.novo", "associados.editar", "associados.alterar_numero",
    "associados.alterar_categoria", "associados.marcar_documento", "associados.adicionar_familiar",
    "associados.remover_familiar", "associados.renovar_qr", "associados.gerar_acesso", "associados.remover_foto",
    "acessos.lista", "acessos.gerar_em_lote",
    "importacao.inicio", "importacao.previa", "importacao.confirmar", "importacao.cancelar", "importacao.modelo",
    "mensalidades.validar", "mensalidades.recusar", "mensalidades.cobranca_mutirantes",
    "assembleias.encerrar", "assembleias.reabrir",
}
# Ações só do presidente
PRESIDENTE = {
    "associados.desligar", "associados.reativar",
    "equipe.lista", "equipe.novo", "equipe.redefinir_senha", "equipe.alternar_ativo", "equipe.alterar_perfil",
    "equipe.baixar_backup",
}


def papel(usuario):
    """Perfil efetivo. Usuários antigos com perfil 'equipe' contam como administração."""
    perfil = getattr(usuario, "perfil", None)
    return "administracao" if perfil == "equipe" else perfil


def pode(acao, usuario=None):
    """acao: 'conferencia', 'presidente' ou o nome de uma rota (ex.: 'mensalidades.validar')."""
    usuario = usuario or current_user
    if not getattr(usuario, "is_authenticated", False):
        return False
    p = papel(usuario)
    if p == "presidente":
        return True
    if acao == "presidente" or acao in PRESIDENTE:
        return False
    if acao == "conferencia" or acao in CONFERENCIA:
        return p == "administracao"
    return True


def conferir_permissao():
    """Roda antes de cada página da equipe: bloqueia (403) o que não é do perfil de quem está logado."""
    if current_user.is_authenticated and request.endpoint and not pode(request.endpoint):
        abort(403)
