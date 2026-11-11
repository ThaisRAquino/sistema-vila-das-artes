"""Backup do sistema: banco de dados, fotos e comprovantes num único arquivo .zip com a data.

Uso:
    python backup.py                 # cria backups/vila-das-artes-AAAA-MM-DD-HHMM.zip
    python backup.py --manter 30     # guarda só os 30 backups mais recentes (padrão: 30)

Na hospedagem, agende para rodar todo dia. Uma vez por semana, baixe o backup mais recente
e guarde fora do servidor (ex.: no Google Drive da associação): backup que fica só no servidor
some junto com ele.
"""
import argparse
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
INSTANCE = os.path.join(BASE, "instance")
PASTA_BACKUP = os.environ.get("VDA_PASTA_BACKUP", os.path.join(BASE, "backups"))


def fazer_backup(manter=30):
    os.makedirs(PASTA_BACKUP, exist_ok=True)
    nome = f"vila-das-artes-{datetime.now():%Y-%m-%d-%H%M}.zip"
    destino = os.path.join(PASTA_BACKUP, nome)
    banco = os.path.join(INSTANCE, "vila_das_artes.db")
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zipado:
        if os.path.exists(banco):
            # cópia segura mesmo com o sistema ligado (API de backup do SQLite)
            copia = os.path.join(tmp, "vila_das_artes.db")
            origem, alvo = sqlite3.connect(banco), sqlite3.connect(copia)
            with alvo:
                origem.backup(alvo)
            origem.close()
            alvo.close()
            zipado.write(copia, "instance/vila_das_artes.db")
        for pasta in ("fotos", "comprovantes"):
            caminho = os.path.join(INSTANCE, pasta)
            for raiz, _, arquivos in os.walk(caminho):
                for arquivo in arquivos:
                    completo = os.path.join(raiz, arquivo)
                    zipado.write(completo, os.path.relpath(completo, BASE))
        chave = os.path.join(INSTANCE, "secret_key")
        if os.path.exists(chave):
            zipado.write(chave, "instance/secret_key")
    antigos = sorted(f for f in os.listdir(PASTA_BACKUP) if f.startswith("vila-das-artes-") and f.endswith(".zip"))
    for velho in antigos[:-manter] if manter > 0 else []:
        os.remove(os.path.join(PASTA_BACKUP, velho))
    tamanho = os.path.getsize(destino) / 1024 / 1024
    print(f"Backup criado: {destino} ({tamanho:.1f} MB)")
    return destino


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Backup do Sistema Vila das Artes")
    argumentos.add_argument("--manter", type=int, default=30, help="quantos backups guardar (padrão 30)")
    fazer_backup(argumentos.parse_args().manter)
