import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

# A planilha é dado interno da FGV e não vai para o repositório: os testes procuram a cópia local.
ENTRADA = sorted((BASE / "entrada").glob("CONCORRENTES_FGV*.xlsx"))
GABARITO = BASE / "gabarito" / "CONCORRENTES_FGV_atualizado_2026-10-05.xlsx"


@pytest.fixture(scope="session")
def entrada():
    if not ENTRADA:
        pytest.skip("cópia da planilha ausente em entrada/")
    return ENTRADA[-1]


@pytest.fixture(scope="session")
def gabarito():
    if not GABARITO.exists():
        pytest.skip("gabarito ausente em gabarito/")
    return GABARITO
