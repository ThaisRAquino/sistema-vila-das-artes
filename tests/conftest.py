"""Configurações comuns dos testes."""
import pytest


@pytest.fixture(autouse=True)
def cobranca_ja_comecou(monkeypatch, request):
    """Os testes antigos supõem a cobrança já valendo; os de início da cobrança usam a marca 'inicio_cobranca_real'."""
    if request.node.get_closest_marker("inicio_cobranca_real"):
        return
    from app import regras
    monkeypatch.setattr(regras, "INICIO_COBRANCA_PADRAO", "2000-01")


def pytest_configure(config):
    config.addinivalue_line("markers", "inicio_cobranca_real: usa o início de cobrança verdadeiro (dez/2026)")
