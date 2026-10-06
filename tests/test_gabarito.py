"""Testes de extração contra os valores conferidos manualmente no LOG do gabarito (05/10/2026).

Baixam os PDFs citados no LOG e comparam taxa, salário e cidades. Precisam de rede: sem acesso, são pulados
(e o motivo aparece no resumo do pytest)."""
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import hashlib

import openpyxl
import pytest
import requests

import normalizacao as N
from extracao import campos, pdf

CERTAMES = ["95/2026", "362/2026", "354/2026", "190/2026", "149/2026", "204/2026", "36/2026", "31/2026",
            "239/2026", "117/2026", "137/2026"]
COLUNAS = {"TAXA", "SALARIO", "CIDADES"}
CACHE = Path(__file__).resolve().parents[1] / "estado" / "cache" / "gabarito"


def _casos(gabarito):
    ws = openpyxl.load_workbook(gabarito, read_only=True)["LOG"]
    linhas = list(ws.iter_rows(values_only=True))
    casos = defaultdict(list)
    for r in linhas[1:]:
        if not r or r[0] not in CERTAMES or r[4] != "CONFIRMADO" or not r[8]:
            continue
        col = N.coluna(r[1])
        if col in COLUNAS and r[3] is not None:
            casos[(r[0], r[8])].append((col, r[3]))
    return casos


def _baixar(url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    destino = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".pdf")
    if not destino.exists():
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "FGV-IC-editais-monitor/0.1 (teste gabarito)"})
            r.raise_for_status()
        except requests.RequestException as e:
            pytest.skip(f"sem acesso a {url}: {e.__class__.__name__}")
        destino.write_bytes(r.content)
    return destino


def pytest_generate_tests(metafunc):
    if "caso" in metafunc.fixturenames:
        from tests.conftest import GABARITO
        casos = _casos(GABARITO) if GABARITO.exists() else {}
        metafunc.parametrize("caso", list(casos.items()), ids=[f"{c}|{u[-40:]}" for c, u in casos])


def test_extracao_bate_com_gabarito(caso):
    (cod, url), esperados = caso
    if not url.lower().split("?")[0].endswith(".pdf") and "stream" not in url:
        pytest.skip("URL do LOG não é PDF")
    pags = pdf.ler(str(_baixar(url)))
    taxas = {t.valor for t in campos.taxa(pags, "", url)}
    salarios = {r["salario"] for r in campos.tabela_cargos(pags, "", url) if r.get("salario") is not None}
    cid = campos.cidades(pags, "", url)
    falhas = []
    for col, valor in esperados:
        if col == "TAXA" and N.dinheiro(valor) not in taxas:
            falhas.append(f"taxa {valor} ∉ {sorted(taxas)}")
        elif col == "SALARIO" and N.dinheiro(valor) not in salarios:
            falhas.append(f"salário {valor} ∉ {sorted(salarios)}")
        elif col == "CIDADES":
            esperado = {N.texto(c) for c in str(valor).split(",")}
            obtido = {N.texto(c) for c in (cid.valor.split(",") if cid else [])}
            if not esperado <= obtido:
                falhas.append(f"cidades {sorted(esperado)} ⊄ {sorted(obtido)}")
    assert not falhas, f"{cod}: " + "; ".join(falhas)
