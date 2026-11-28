"""Arquivos dos documentos do associado (RG, CPF, comprovante de endereço...).

Podem ser enviados pelo próprio associado, na área dele, ou pela equipe, na ficha.
Ficam guardados com nome aleatório numa pasta fora do site e só a conferência vê.
"""
import os
from datetime import datetime

from flask import current_app

from .mensalidades import salvar_comprovante


def pasta_documentos():
    pasta = os.path.join(current_app.instance_path, "documentos")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def apagar_arquivo(documento):
    if documento.arquivo:
        caminho = os.path.join(pasta_documentos(), documento.arquivo)
        if os.path.exists(caminho):
            os.remove(caminho)
    documento.arquivo = None


def salvar_documento(documento, arquivo, pelo_associado):
    """Guarda o arquivo e deixa o documento "em análise". Devolve uma mensagem de erro ou None."""
    nome, erro = salvar_comprovante(arquivo, pasta_documentos())
    if erro:
        return erro.replace("do comprovante", "do documento")
    apagar_arquivo(documento)  # troca o arquivo anterior, se houver
    documento.arquivo = nome
    documento.status = "em_analise"
    documento.enviado_em = datetime.now()
    documento.enviado_pelo_associado = pelo_associado
    documento.motivo_recusa = None
    documento.conferido_por_id = None
    documento.conferido_em = None
    return None
