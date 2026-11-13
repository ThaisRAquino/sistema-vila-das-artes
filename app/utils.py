"""Funções auxiliares: CPF, datas e valores em reais."""
import re
from datetime import date, datetime


def somente_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def cpf_valido(cpf):
    """Valida os dígitos verificadores do CPF."""
    cpf = somente_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def formatar_cpf(cpf):
    cpf = somente_digitos(cpf)
    if len(cpf) != 11:
        return cpf or ""
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def formatar_cep(cep):
    """06803-000"""
    cep = somente_digitos(cep)
    return f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else (cep or "")


def mascarar_cpf(cpf):
    """Mostra só o miolo do CPF (LGPD): ***.456.789-**"""
    cpf = somente_digitos(cpf)
    if len(cpf) != 11:
        return ""
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"


def formatar_data(valor):
    if not valor:
        return ""
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def ler_data(texto):
    """Aceita dd/mm/aaaa ou aaaa-mm-dd (campo date do navegador)."""
    texto = (texto or "").strip()
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida: {texto}")


def ler_valor(texto):
    """Converte '1.850,50' ou '1850.50' em float."""
    texto = (texto or "").strip().replace("R$", "").strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return round(float(texto), 2)
    except ValueError:
        raise ValueError(f"Valor inválido: {texto}")


def formatar_moeda(valor):
    if valor is None:
        return ""
    inteiro, centavos = f"{valor:,.2f}".split(".")
    return "R$ " + inteiro.replace(",", ".") + "," + centavos
