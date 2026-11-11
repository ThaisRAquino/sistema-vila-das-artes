"""Liga o sistema para TESTAR no computador: python run.py  →  abra http://127.0.0.1:5000

Atenção: este modo (debug) é só para testes no seu computador. Para publicar na internet use o wsgi.py
(veja a seção "Publicar" do README).
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
