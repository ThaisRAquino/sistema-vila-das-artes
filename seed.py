"""Cria o primeiro usuário da equipe e, se pedido, alguns associados de exemplo.

Uso:
    python seed.py                 # cria só o usuário admin
    python seed.py --exemplos      # cria o admin e 6 associados fictícios para teste
    python seed.py --nova-senha    # troca a senha do admin (se esqueceu), sem apagar nada
"""
import getpass
import sys
from datetime import date, datetime

from app import create_app, db
from app.models import Assembleia, Associado, Mensalidade, Presenca, Usuario
from app.regras import competencia_anterior, competencia_atual, garantir_mensalidades, proximo_recibo, segundo_domingo

# CPFs fictícios, mas com dígitos verificadores válidos (só para teste)
EXEMPLOS = [
    ("0142", "Ana Paula Souza Lima", "52998224725", "regular", date(2019, 3, 10), 3),
    ("0231", "José Carlos Ferreira", "11144477735", "regular", date(2017, 8, 2), 5),
    ("0057", "Maria das Graças Ribeiro", "39053344705", "mutirante", date(2012, 2, 20), 5),
    ("0418", "Edson Oliveira Santos", "86288366757", "regular", date(2024, 5, 4), 3),
    ("0502", "Cláudia Mendes", "15350946056", "regular", date(2026, 9, 12), 5),
    ("0377", "Rosana Alves", "74682489070", "regular", date(2021, 6, 1), 4),
]


def pedir_senha():
    """Pede a senha duas vezes (a digitação não aparece na tela)."""
    if not sys.stdin.isatty():
        print("Senha do admin: trocar123 (troque depois com: python seed.py --nova-senha)")
        return "trocar123"
    print("A senha não aparece enquanto você digita. Isso é normal.")
    while True:
        senha = getpass.getpass("Senha do usuário admin (mínimo 6 caracteres): ")
        if len(senha) < 6:
            print("Muito curta. Tente de novo.")
            continue
        if getpass.getpass("Repita a senha: ") != senha:
            print("As senhas não são iguais. Tente de novo.")
            continue
        return senha


def trocar_senha_admin():
    usuario = db.session.execute(db.select(Usuario).filter_by(login="admin")).scalar_one_or_none()
    if not usuario:
        print("Usuário 'admin' não existe. Rode: python seed.py")
        return
    usuario.definir_senha(pedir_senha())
    usuario.ativo = True
    db.session.commit()
    print("Senha do admin trocada. Entre com o usuário admin e a senha nova.")


def criar_admin():
    if db.session.execute(db.select(Usuario).filter_by(login="admin")).scalar_one_or_none():
        print("Usuário 'admin' já existe. Esqueceu a senha? Rode: python seed.py --nova-senha")
        return
    senha = pedir_senha()
    usuario = Usuario(nome="Administrador", login="admin", perfil="presidente")
    usuario.definir_senha(senha)
    db.session.add(usuario)
    db.session.commit()
    print("Usuário 'admin' criado.")


def criar_exemplos():
    for numero, nome, cpf, categoria, inscricao, entregues in EXEMPLOS:
        if db.session.execute(db.select(Associado).filter_by(cpf=cpf)).scalar_one_or_none():
            continue
        a = Associado(
            numero_socio=numero, nome=nome, cpf=cpf, categoria=categoria,
            data_inscricao=inscricao, cidade="Embu das Artes", uf="SP", bairro="Jardim Nayara",
            celular="(11) 90000-" + numero,  # número fictício
        )
        a.criar_checklist()
        for documento in a.documentos[:entregues]:
            documento.status = "entregue"
        db.session.add(a)
    db.session.commit()
    criar_historico()
    print("Associados, mensalidades e assembleias de exemplo criados (dados fictícios).")
    from app.area_associado import gerar_codigo_acesso
    from app.utils import formatar_cpf

    ana = db.session.execute(db.select(Associado).filter_by(numero_socio="0142")).scalar_one_or_none()
    if ana and not ana.senha_hash:
        codigo = gerar_codigo_acesso(ana)
        db.session.commit()
        print(f"Para testar a área do associado: /associado/primeiro-acesso  CPF {formatar_cpf(ana.cpf)}  código {codigo}")


def criar_historico():
    """3 meses de mensalidades e 3 assembleias passadas, para o painel mostrar alertas."""
    admin = db.session.execute(db.select(Usuario).filter_by(login="admin")).scalar_one()
    atual = competencia_atual()
    meses = [competencia_anterior(atual, i) for i in (3, 2, 1)]
    for mes in meses + [atual]:
        garantir_mensalidades(mes)
    atrasados = {"0231"}            # José: 3 mensalidades seguidas em aberto
    for m in db.session.execute(db.select(Mensalidade)).scalars():
        if m.status != "aberta" or m.competencia == atual or m.associado.numero_socio in atrasados:
            continue
        m.status, m.forma, m.validado_por_id = "paga", "pix", admin.id
        m.validado_em = datetime.now()
        m.numero_recibo = proximo_recibo(m.competencia)
        db.session.flush()

    faltosos = {"0418": 3, "0142": 2}  # Edson: 3 faltas; Ana: 2 faltas
    datas = [segundo_domingo(int(mes[:4]), int(mes[5:])) for mes in meses]
    for i, data in enumerate(sorted(d for d in datas if d < date.today())):
        if db.session.execute(db.select(Assembleia).filter_by(data=data)).scalar_one_or_none():
            continue
        asm = Assembleia(data=data, encerrada=True)
        db.session.add(asm)
        db.session.flush()
        for a in db.session.execute(db.select(Associado)).scalars():
            faltas = faltosos.get(a.numero_socio, 0)
            if i >= 3 - faltas or (a.data_inscricao and a.data_inscricao > data):
                continue
            db.session.add(Presenca(assembleia_id=asm.id, associado_id=a.id, registrado_por_id=admin.id))
    db.session.commit()


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        if "--nova-senha" in sys.argv:
            trocar_senha_admin()
            sys.exit()
        criar_admin()
        if "--exemplos" in sys.argv:
            criar_exemplos()
