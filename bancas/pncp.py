"""Radar PNCP: contratos firmados entre órgãos públicos e as bancas monitoradas.

Por que existe (08/10/2026): os sites de FCC, Vunesp, IDECAN, IBFC e os PDFs da AOCP bloqueiam leitura automática,
então a lista de certames dessas bancas ficava incompleta. O PNCP (fonte oficial, Lei 14.133) publica a contratação
da banca — normalmente dispensa do art. 75, XV — com órgão, UF, município, data de assinatura, valor global e o
fornecedor (nome e CNPJ). O PNCP NÃO traz cargos, salários nem taxas: isso continua vindo do edital.

O contrato costuma ser assinado meses antes do edital. Por isso cada contrato entra numa lista persistente
(estado/radar_pncp.json) com situação "aguardando edital" e é reconferido a cada rodada até o edital do órgão aparecer.
Busca de 18 meses para trás: contrato de 2025 pode ter edital publicado em 2026.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import normalizacao as N

API = "https://pncp.gov.br/api/search/?q={q}&tipos_documento=contrato&ordenacao=-data&pagina={p}&tam_pagina=50"
LINK = "https://pncp.gov.br/app/contratos/{cnpj}/{ano}/{seq}"

# termo de busca e nome do fornecedor esperado (o termo aparece em qualquer campo; o fornecedor confirma a banca)
BANCAS = {
    "cebraspe": ('"cebraspe"', r"CEBRASPE|CENTRO BRASILEIRO DE PESQUISA EM AVALIACAO E SELECAO"),
    "fcc": ('"fundação carlos chagas"', r"FUNDACAO CARLOS CHAGAS"),
    "cesgranrio": ('"cesgranrio"', r"CESGRANRIO"),
    "vunesp": ('"vunesp"', r"VUNESP|FUNDACAO PARA O VESTIBULAR DA UNIVERSIDADE ESTADUAL PAULISTA"),
    "idecan": ('"idecan"', r"IDECAN|INSTITUTO DE DESENVOLVIMENTO EDUCACIONAL, CULTURAL E ASSISTENCIAL NACIONAL"),
    "aocp": ('"instituto aocp"', r"\bAOCP\b"),
    "ibfc": ('"ibfc"', r"\bIBFC\b|INSTITUTO BRASILEIRO DE FORMACAO E CAPACITACAO"),
}
_OBJETO = re.compile(r"CONCURSO|PROCESSO SELETIVO|SELECAO PUBLICA|VESTIBULAR|RESIDENCIA|EXAME DE")


def _texto(v) -> str:
    """O PNCP devolve alguns campos como lista (ex.: amparo legal)."""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    return "" if v is None else str(v).strip("[]'\"")


def _get_json(acesso, url: str, banca: str, tentativas: int = 3):
    for i in range(tentativas):
        try:
            return json.loads(acesso.texto(url, banca))
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(5 * (i + 1))          # o PNCP oscila (respostas vazias/tempo esgotado); nova tentativa


def buscar(acesso, chave: str, meses: int = 18, max_paginas: int = 6) -> list[dict]:
    """Contratos da banca (fornecedor conferido) com objeto de concurso/seleção, assinados nos últimos `meses`."""
    termo, rx = BANCAS[chave]
    corte = (date.today() - timedelta(days=30 * meses)).isoformat()
    out = []
    for p in range(1, max_paginas + 1):
        d = _get_json(acesso, API.format(q=quote(termo), p=p), chave)
        itens = d.get("items") or []
        for it in itens:
            if str(it.get("cancelado")) == "True":
                continue
            if not re.search(rx, N.texto(it.get("fornecedor_nome"))):
                continue                      # banca citada no texto, mas não é a contratada
            if not _OBJETO.search(N.texto(it.get("description"))):
                continue
            if (it.get("data_assinatura") or "") < corte:
                continue
            cnpj, ano, seq = (it.get("item_url") or "///").strip("/").split("/")[-3:]
            out.append({
                "banca": chave, "id": it.get("numero_controle_pncp"),
                "orgao": it.get("orgao_nome"), "unidade": it.get("unidade_nome"), "uf": it.get("uf"),
                "municipio": it.get("municipio_nome"), "esfera": it.get("esfera_nome"),
                "objeto": " ".join((it.get("description") or "").split()), "valor_global": it.get("valor_global"),
                "data_assinatura": it.get("data_assinatura"), "fundamento": _texto(it.get("amparo_legal_nome")),
                "fornecedor": it.get("fornecedor_nome"), "fornecedor_cnpj": it.get("fornecedor_ni"),
                "link": LINK.format(cnpj=cnpj, ano=ano, seq=seq),
            })
        datas = [it.get("data_assinatura") or "" for it in itens]
        if len(itens) < 50 or (datas and max(datas) < corte):
            break
    return out


def atualizar_radar(estado_dir: Path, novos: list[dict]) -> dict:
    """Junta os contratos novos à lista persistente. Contrato já conhecido mantém a situação registrada."""
    arq = estado_dir / "radar_pncp.json"
    radar = json.loads(arq.read_text()) if arq.exists() else {}
    hoje = date.today().isoformat()
    for c in novos:
        atual = radar.get(c["id"], {"situacao": "aguardando edital", "visto_em": hoje})
        radar[c["id"]] = {**atual, **c}
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(radar, ensure_ascii=False, indent=1))
    return radar


def salvar_radar(estado_dir: Path, radar: dict) -> None:
    (estado_dir / "radar_pncp.json").write_text(json.dumps(radar, ensure_ascii=False, indent=1))


def mesmo_orgao(contrato: dict, cliente: str, uf: str = "") -> bool:
    """O contrato do PNCP é do mesmo órgão do certame? Órgão contratante às vezes é a secretaria-meio
    (ex.: Secretaria de Administração contrata para a Polícia Civil), então compara órgão e unidade."""
    tc = N.orgao_tokens(cliente) - {"ESTADO", "MUNICIPAL", "PREFEITURA"}
    if uf and contrato.get("uf") and uf != contrato["uf"]:
        return False
    for nome in (contrato.get("orgao"), contrato.get("unidade")):
        to = N.orgao_tokens(nome) - {"ESTADO", "MUNICIPAL", "PREFEITURA"}
        if tc and to and len(tc & to) / len(tc | to) >= 0.6:
            return True
    return False
