"""Ponto de entrada para a hospedagem (servidor de produção).

Na hospedagem, configure:
  - a variável de ambiente VDA_PRODUCAO=1
  - a variável SECRET_KEY com uma chave longa e secreta (ou deixe o sistema criar em instance/secret_key)
  - o servidor apontando para  wsgi:app   (ex.: gunicorn wsgi:app   ou   waitress-serve wsgi:app)

Não use  python run.py  na internet: ele é só para testar no computador.
"""
from app import create_app

app = create_app()
