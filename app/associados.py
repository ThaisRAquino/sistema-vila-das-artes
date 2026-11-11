"""Cadastro de associados: lista, ficha, novo, edição, nº de sócio, documentos e QR."""
import io
from datetime import date, datetime

import qrcode
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from . import db
from .models import (
    CATEGORIAS,
    ESTADOS_CIVIS,
    TIPOS_RESIDENCIA,
    Associado,
    Documento,
    Familiar,
    HistoricoNumeroSocio,
    novo_codigo_qr,
)
from .utils import cpf_valido, ler_data, ler_valor, somente_digitos

bp = Blueprint("associados", __name__, url_prefix="/associados")

# campo do formulário -> tipo de conversão
CAMPOS = {
    "nome": "texto", "cpf": "cpf", "rg": "texto", "orgao_emissor": "texto", "uf_rg": "uf",
    "data_emissao_rg": "data", "data_nascimento": "data", "nacionalidade": "texto",
    "naturalidade": "texto", "nome_pai": "texto", "nome_mae": "texto", "estado_civil": "texto",
    "grau_instrucao": "texto", "profissao": "texto", "renda": "valor", "empresa": "texto",
    "cnpj": "digitos", "data_admissao": "data", "ctps": "texto", "serie_ctps": "texto",
    "titulo_eleitor": "texto", "celular": "texto", "tel_residencial": "texto", "recado": "texto",
    "email": "texto", "rua": "texto", "numero": "texto", "bairro": "texto", "cidade": "texto",
    "uf": "uf", "cep": "digitos", "tipo_residencia": "texto", "valor_aluguel": "valor",
    "renda_familiar_total": "valor", "categoria": "texto",
    "data_inscricao": "data",
}


def formatar_numero(numero):
    """Nº de sócio sempre com 4 dígitos: 7 -> 0007."""
    digitos = somente_digitos(numero)
    return digitos.zfill(4) if digitos else ""


def proximo_numero():
    numeros = db.session.execute(db.select(Associado.numero_socio)).scalars().all()
    maior = max((int(n) for n in numeros if n.isdigit()), default=0)
    return str(maior + 1).zfill(4)


def numero_em_uso(numero, ignorar_id=None):
    consulta = db.select(Associado.id).filter_by(numero_socio=numero)
    if ignorar_id:
        consulta = consulta.filter(Associado.id != ignorar_id)
    return db.session.execute(consulta).first() is not None


def preencher(associado, form):
    """Copia os campos do formulário para o associado e devolve a lista de erros."""
    erros = []
    for campo, tipo in CAMPOS.items():
        bruto = form.get(campo, "")
        try:
            if tipo == "data":
                valor = ler_data(bruto)
            elif tipo == "valor":
                valor = ler_valor(bruto)
            elif tipo in ("cpf", "digitos"):
                valor = somente_digitos(bruto) or None
            elif tipo == "uf":
                valor = bruto.strip().upper()[:2] or None
            else:
                valor = bruto.strip() or None
        except ValueError as erro:
            erros.append(str(erro))
            continue
        setattr(associado, campo, valor)

    if not associado.nome:
        erros.append("Informe o nome completo do titular.")
    if not associado.cpf or not cpf_valido(associado.cpf):
        erros.append("CPF inválido.")
    else:
        repetido = db.select(Associado).filter_by(cpf=associado.cpf)
        if associado.id:
            repetido = repetido.filter(Associado.id != associado.id)
        with db.session.no_autoflush:
            outro = db.session.execute(repetido).scalar_one_or_none()
        if outro:
            erros.append(f"Este CPF já está cadastrado no sócio nº {outro.numero_socio} ({outro.nome}).")
    if associado.categoria not in CATEGORIAS:
        associado.categoria = "regular"
    return erros


def buscar(associado_id):
    associado = db.session.get(Associado, associado_id)
    if not associado:
        abort(404)
    return associado


FILTROS = {
    "todos": "Todos",
    "regular": "Regulares",
    "mutirante": "Mutirantes",
    "pendentes": "Documentação pendente",
    "completos": "Documentação completa",
    "desligados": "Desligados",
}


def consulta_lista(termo, filtro):
    """Consulta usada na lista e na exportação (a planilha sai com os mesmos filtros da tela)."""
    situacao = "desligado" if filtro == "desligados" else "ativo"
    consulta = db.select(Associado).filter_by(situacao=situacao)
    if termo:
        digitos = somente_digitos(termo)
        condicoes = [Associado.nome.ilike(f"%{termo}%")]
        if digitos:
            condicoes += [Associado.cpf.contains(digitos), Associado.numero_socio == digitos.zfill(4)]
        consulta = consulta.filter(or_(*condicoes))
    if filtro in CATEGORIAS:
        consulta = consulta.filter_by(categoria=filtro)
    elif filtro == "pendentes":
        consulta = consulta.filter(Associado.documentos.any(Documento.status == "pendente"))
    elif filtro == "completos":
        consulta = consulta.filter(~Associado.documentos.any(Documento.status == "pendente"))
    return consulta.order_by(Associado.numero_socio)


@bp.route("/")
@login_required
def lista():
    termo = request.args.get("q", "").strip()
    filtro = request.args.get("filtro", "todos")
    if filtro not in FILTROS:
        filtro = "todos"
    associados = db.session.execute(consulta_lista(termo, filtro)).scalars().all()

    contagem = dict(
        db.session.execute(
            db.select(Associado.categoria, func.count()).filter_by(situacao="ativo").group_by(Associado.categoria)
        ).all()
    )
    pendentes = db.session.execute(
        db.select(func.count(func.distinct(Documento.associado_id)))
        .join(Associado)
        .filter(Documento.status == "pendente", Associado.situacao == "ativo")
    ).scalar()
    desligados = db.session.execute(
        db.select(func.count()).select_from(Associado).filter_by(situacao="desligado")
    ).scalar()
    total = contagem.get("regular", 0) + contagem.get("mutirante", 0)
    return render_template(
        "associados/lista.html",
        associados=associados,
        termo=termo,
        filtro=filtro,
        contagem=contagem,
        pendentes=pendentes,
        completos=total - pendentes,
        desligados=desligados,
        filtros=FILTROS,
    )


@bp.route("/exportar.xlsx")
@login_required
def exportar():
    """Lista em Excel com os mesmos filtros da tela (ex.: a lista pedida pelo CDHU ou pela Prefeitura)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    from .models import RegistroExportacao
    from .regras import situacao as situacao_de
    from .utils import formatar_cpf

    termo = request.args.get("q", "").strip()
    filtro = request.args.get("filtro", "todos")
    if filtro not in FILTROS:
        filtro = "todos"
    associados = db.session.execute(consulta_lista(termo, filtro)).scalars().all()

    livro = Workbook()
    aba = livro.active
    aba.title = "Associados"
    colunas = [
        ("Nº de sócio", 11), ("Nome completo", 36), ("CPF", 16), ("RG", 14), ("Data de nascimento", 14),
        ("Categoria", 12), ("Data de inscrição", 14), ("Estado civil", 12), ("Profissão", 18),
        ("Renda (R$)", 12), ("Renda familiar total (R$)", 14), ("Nº de familiares", 11),
        ("Celular", 16), ("E-mail", 26), ("Endereço", 40), ("Bairro", 18), ("Cidade", 16), ("UF", 5),
        ("CEP", 10), ("Tipo de residência", 16), ("Documentos entregues", 12), ("Documentos pendentes", 34),
        ("Faltas seguidas", 10), ("Mensalidades em aberto", 12), ("Situação", 12),
    ]
    aba.append([nome for nome, _ in colunas])
    for a in associados:
        s = situacao_de(a) if a.situacao == "ativo" else None
        endereco = ", ".join(p for p in [a.rua, a.numero] if p)
        pendentes = [d.tipo for d in a.documentos if d.status == "pendente"]
        aba.append([
            a.numero_socio, a.nome, formatar_cpf(a.cpf), a.rg or "",
            a.data_nascimento.strftime("%d/%m/%Y") if a.data_nascimento else "",
            "Mutirante" if a.mutirante else "Regular",
            a.data_inscricao.strftime("%d/%m/%Y") if a.data_inscricao else "",
            a.estado_civil or "", a.profissao or "", a.renda, a.renda_familiar_total, len(a.familiares),
            a.celular or "", a.email or "", endereco, a.bairro or "", a.cidade or "", a.uf or "", a.cep or "",
            a.tipo_residencia or "", f"{a.docs_entregues} de {a.docs_total}", ", ".join(pendentes),
            s["faltas"] if s else "", s["atrasadas"] if s else "",
            {"ok": "Em dia", "atencao": "Atenção", "risco": "Risco"}[s["nivel"]] if s else "Desligado",
        ])
    for celula in aba[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="2B3F8F")
        celula.alignment = Alignment(wrap_text=True, vertical="center")
    for indice, (_, largura) in enumerate(colunas, start=1):
        aba.column_dimensions[aba.cell(row=1, column=indice).column_letter].width = largura
    for linha in aba.iter_rows(min_row=2, min_col=10, max_col=11):
        for celula in linha:
            celula.number_format = "#,##0.00"
    aba.freeze_panes = "C2"
    aba.auto_filter.ref = aba.dimensions

    descricao = FILTROS[filtro] + (f" · busca: {termo}" if termo else "")
    db.session.add(RegistroExportacao(usuario_id=current_user.id, filtros=descricao[:200], quantidade=len(associados)))
    db.session.commit()

    saida = io.BytesIO()
    livro.save(saida)
    saida.seek(0)
    nome = f"associados-{filtro}-{date.today():%Y-%m-%d}.xlsx"
    return send_file(saida, as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def presidente_obrigatorio():
    if not current_user.presidente:
        abort(403)


@bp.route("/<int:associado_id>/desligar", methods=["POST"])
@login_required
def desligar(associado_id):
    """Registra a decisão da diretoria. O sistema nunca desliga ninguém sozinho."""
    from .models import MOTIVOS_DESLIGAMENTO, HistoricoSituacao

    presidente_obrigatorio()
    associado = buscar(associado_id)
    motivo = request.form.get("motivo", "")
    try:
        data_decisao = ler_data(request.form.get("data_decisao")) or date.today()
    except ValueError:
        data_decisao = None
    if associado.situacao != "ativo":
        flash("Este associado já está desligado.", "aviso")
    elif motivo not in MOTIVOS_DESLIGAMENTO:
        flash("Escolha o motivo do desligamento.", "erro")
    elif not data_decisao:
        flash("Data da decisão inválida.", "erro")
    else:
        associado.situacao = "desligado"
        db.session.add(HistoricoSituacao(
            associado=associado, situacao="desligado", motivo=motivo,
            observacao=(request.form.get("observacao") or "").strip()[:300] or None,
            data_decisao=data_decisao, registrado_por_id=current_user.id,
        ))
        db.session.commit()
        flash(f"Desligamento de {associado.nome} registrado. Ele sai das listas, das mensalidades e da área do associado. "
              "O histórico continua guardado e é possível reativar.", "ok")
    return redirect(url_for("associados.ficha", associado_id=associado.id))


@bp.route("/<int:associado_id>/reativar", methods=["POST"])
@login_required
def reativar(associado_id):
    from .models import HistoricoSituacao

    presidente_obrigatorio()
    associado = buscar(associado_id)
    if associado.situacao == "ativo":
        flash("Este associado já está ativo.", "aviso")
    else:
        associado.situacao = "ativo"
        db.session.add(HistoricoSituacao(
            associado=associado, situacao="ativo", motivo="Reativado pela diretoria",
            observacao=(request.form.get("observacao") or "").strip()[:300] or None,
            data_decisao=date.today(), registrado_por_id=current_user.id,
        ))
        db.session.commit()
        flash(f"{associado.nome} foi reativado(a). As mensalidades voltam a ser geradas a partir deste mês.", "ok")
    return redirect(url_for("associados.ficha", associado_id=associado.id))


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    associado = Associado(categoria="regular", cidade="Embu das Artes", uf="SP", data_inscricao=date.today())
    numero = proximo_numero()
    if request.method == "POST":
        numero = formatar_numero(request.form.get("numero_socio"))
        erros = preencher(associado, request.form)
        if not numero:
            erros.append("Informe o nº de sócio.")
        elif numero_em_uso(numero):
            erros.append(f"O nº de sócio {numero} já está em uso. Sugestão: {proximo_numero()}.")
        if not request.form.get("consentimento"):
            erros.append("Marque a autorização de uso dos dados (LGPD).")
        if not erros:
            associado.numero_socio = numero
            associado.qr_codigo = novo_codigo_qr()
            associado.consentimento_lgpd_em = datetime.now()
            associado.criar_checklist()
            db.session.add(associado)
            db.session.commit()
            flash(f"Associado cadastrado com o nº de sócio {numero}.", "ok")
            return redirect(url_for("associados.ficha", associado_id=associado.id))
        for erro in erros:
            flash(erro, "erro")
    return render_template(
        "associados/form.html",
        associado=associado,
        numero=numero,
        novo=True,
        estados_civis=ESTADOS_CIVIS,
        tipos_residencia=TIPOS_RESIDENCIA,
    )


@bp.route("/<int:associado_id>")
@login_required
def ficha(associado_id):
    from .models import Assembleia
    from .regras import competencia_atual, garantir_mensalidades

    associado = buscar(associado_id)
    garantir_mensalidades(competencia_atual())
    inscricao = associado.data_inscricao or associado.criado_em.date()
    assembleias_recentes = db.session.execute(
        db.select(Assembleia).filter(Assembleia.data >= inscricao).order_by(Assembleia.data.desc()).limit(6)
    ).scalars().all()
    from .models import MOTIVOS_DESLIGAMENTO

    return render_template("associados/ficha.html", a=associado, assembleias_recentes=assembleias_recentes,
                           motivos_desligamento=MOTIVOS_DESLIGAMENTO, hoje=date.today())


@bp.route("/<int:associado_id>/editar", methods=["GET", "POST"])
@login_required
def editar(associado_id):
    associado = buscar(associado_id)
    if request.method == "POST":
        erros = preencher(associado, request.form)
        if not erros:
            db.session.commit()
            flash("Ficha atualizada.", "ok")
            return redirect(url_for("associados.ficha", associado_id=associado.id))
        db.session.rollback()
        for erro in erros:
            flash(erro, "erro")
        associado = buscar(associado_id)
    return render_template(
        "associados/form.html",
        associado=associado,
        numero=associado.numero_socio,
        novo=False,
        estados_civis=ESTADOS_CIVIS,
        tipos_residencia=TIPOS_RESIDENCIA,
    )


@bp.route("/<int:associado_id>/numero", methods=["POST"])
@login_required
def alterar_numero(associado_id):
    """A equipe pode trocar o nº de sócio; o sistema bloqueia repetidos e guarda o histórico."""
    associado = buscar(associado_id)
    novo_numero = formatar_numero(request.form.get("numero_socio"))
    motivo = request.form.get("motivo", "").strip() or None
    if not novo_numero:
        flash("Informe o novo nº de sócio.", "erro")
    elif novo_numero == associado.numero_socio:
        flash("O número informado é o mesmo de hoje.", "aviso")
    elif numero_em_uso(novo_numero, ignorar_id=associado.id):
        flash(f"O nº {novo_numero} já pertence a outro associado. Escolha outro.", "erro")
    else:
        db.session.add(
            HistoricoNumeroSocio(
                associado=associado,
                numero_anterior=associado.numero_socio,
                numero_novo=novo_numero,
                motivo=motivo,
                alterado_por_id=current_user.id,
            )
        )
        associado.numero_socio = novo_numero
        db.session.commit()
        flash(f"Nº de sócio alterado para {novo_numero}.", "ok")
    return redirect(url_for("associados.ficha", associado_id=associado.id))


@bp.route("/<int:associado_id>/categoria", methods=["POST"])
@login_required
def alterar_categoria(associado_id):
    associado = buscar(associado_id)
    categoria = request.form.get("categoria")
    if categoria in CATEGORIAS:
        associado.categoria = categoria
        db.session.commit()
        flash(f"Categoria alterada para {categoria}.", "ok")
    return redirect(url_for("associados.ficha", associado_id=associado.id))


@bp.route("/<int:associado_id>/documentos/<int:documento_id>", methods=["POST"])
@login_required
def marcar_documento(associado_id, documento_id):
    documento = db.session.get(Documento, documento_id)
    if not documento or documento.associado_id != associado_id:
        abort(404)
    if documento.status == "entregue":
        documento.status = "pendente"
        documento.conferido_por_id = None
        documento.conferido_em = None
    else:
        documento.status = "entregue"
        documento.conferido_por_id = current_user.id
        documento.conferido_em = datetime.now()
    db.session.commit()
    return redirect(url_for("associados.ficha", associado_id=associado_id) + "#documentos")


@bp.route("/<int:associado_id>/familiares", methods=["POST"])
@login_required
def adicionar_familiar(associado_id):
    associado = buscar(associado_id)
    nome = request.form.get("nome", "").strip()
    tipo = request.form.get("tipo", "dependente")
    if not nome:
        flash("Informe o nome do familiar.", "erro")
    else:
        try:
            familiar = Familiar(
                tipo=tipo if tipo in ("cônjuge", "dependente") else "dependente",
                nome=nome,
                cpf=somente_digitos(request.form.get("cpf")) or None,
                data_nascimento=ler_data(request.form.get("data_nascimento")),
                renda=ler_valor(request.form.get("renda")),
            )
        except ValueError as erro:
            flash(str(erro), "erro")
        else:
            associado.familiares.append(familiar)
            db.session.commit()
            flash(f"{nome} adicionado(a) à família.", "ok")
    return redirect(url_for("associados.ficha", associado_id=associado.id) + "#familia")


@bp.route("/<int:associado_id>/familiares/<int:familiar_id>/remover", methods=["POST"])
@login_required
def remover_familiar(associado_id, familiar_id):
    familiar = db.session.get(Familiar, familiar_id)
    if not familiar or familiar.associado_id != associado_id:
        abort(404)
    db.session.delete(familiar)
    db.session.commit()
    flash("Familiar removido.", "ok")
    return redirect(url_for("associados.ficha", associado_id=associado_id) + "#familia")


@bp.route("/<int:associado_id>/qr.png")
@login_required
def qr(associado_id):
    """Imagem do QR da carteirinha, gerada a partir do código secreto do associado."""
    associado = buscar(associado_id)
    imagem = qrcode.make(associado.qr_codigo, box_size=8, border=2)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@bp.route("/<int:associado_id>/qr/renovar", methods=["POST"])
@login_required
def renovar_qr(associado_id):
    """Gera um código novo (carteirinha perdida); o QR antigo deixa de funcionar."""
    associado = buscar(associado_id)
    associado.qr_codigo = novo_codigo_qr()
    db.session.commit()
    flash("Novo QR gerado. O QR anterior não vale mais.", "ok")
    return redirect(url_for("associados.ficha", associado_id=associado.id))


@bp.route("/<int:associado_id>/acesso", methods=["POST"])
@login_required
def gerar_acesso(associado_id):
    """Gera o código de primeiro acesso (ou de troca de senha) da área do associado."""
    from .area_associado import gerar_codigo_acesso

    associado = buscar(associado_id)
    codigo = gerar_codigo_acesso(associado)
    db.session.commit()
    flash(f"Código de acesso de {associado.nome}: {codigo} (vale 7 dias). Envie pelo WhatsApp ou entregue em mãos.", "ok")
    return redirect(url_for("associados.ficha", associado_id=associado.id) + "#acesso")


@bp.route("/<int:associado_id>/foto.jpg")
@login_required
def foto(associado_id):
    from flask import send_from_directory

    from .area_associado import pasta_fotos

    associado = buscar(associado_id)
    if not associado.foto:
        abort(404)
    return send_from_directory(pasta_fotos(), associado.foto)


@bp.route("/<int:associado_id>/foto/remover", methods=["POST"])
@login_required
def remover_foto(associado_id):
    from .area_associado import apagar_foto

    associado = buscar(associado_id)
    apagar_foto(associado)
    db.session.commit()
    flash("Foto removida. O associado pode enviar outra pela área do associado.", "ok")
    return redirect(url_for("associados.ficha", associado_id=associado.id) + "#acesso")
