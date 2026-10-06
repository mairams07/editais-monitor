"""Deduplicação: o certame da banca já está na planilha (FGV recebeu a demanda) ou é EXTERNO?

Compara com TODAS as linhas das abas de deduplicação (2025 e 2026), de qualquer banca e qualquer situação.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

import normalizacao as N
from modelos import Certame
from planilha import Aba


@dataclass
class Candidato:
    aba: str
    linha: int
    cod_interno: str | None
    cliente: str
    banca: str | None
    situacao: str | None
    score: float


@dataclass
class Resultado:
    decisao: str                 # EXTERNO | JA_NA_PLANILHA | AMBIGUO
    candidatos: list[Candidato]


# Palavras que aparecem em nomes de muitos órgãos e não identificam nenhum ("Prefeitura Municipal de …").
_GENERICOS = {"PREFEITURA", "MUNICIPAL", "MUNICIPIO", "CAMARA", "SECRETARIA", "ESTADO", "ESTADUAL", "GOVERNO",
              "INSTITUTO", "FUNDACAO", "CONCURSO", "PUBLICO", "PUBLICA", "SERVICO", "AUTONOMO", "ORGAO", "NACIONAL",
              "GERAL", "REGIONAL", "SUPERIOR", "EDUCACAO", "CIENCIA", "TECNOLOGIA"}


def _score(certame: Certame, linha: dict) -> float:
    cli = linha.get("CLIENTE") or ""
    to = N.orgao_tokens(certame.orgao) - _GENERICOS
    tc = N.orgao_tokens(cli) - _GENERICOS
    if not to:
        return 0.0
    # 1) órgão do edital × CLIENTE
    s_cli = 0.0
    if tc and to & tc:
        jacc = 100 * len(to & tc) / len(to | tc)
        fz = fuzz.token_set_ratio(" ".join(sorted(to)), " ".join(sorted(tc)))
        s_cli = 0.5 * jacc + 0.5 * fz
    # 2) órgão do edital citado no OBJETO — cobre demanda registrada no órgão contratante
    #    (ex.: PC-PE dentro da demanda da Secretaria de Administração de PE)
    s_obj = 0.0
    tobj = N.orgao_tokens(linha.get("OBJETO"))
    if len(to) >= 2 and to & tobj:
        s_obj = 90 * len(to & tobj) / len(to)
    s = max(s_cli, s_obj)
    if s == 0:
        return 0.0
    uf = N.texto(linha.get("UF")) or N.uf_no_texto(cli) or N.uf_no_texto(linha.get("OBJETO"))
    uf_cert = (certame.uf or N.uf_no_texto(certame.orgao) or "").upper()
    if uf_cert and uf:
        s += 5 if uf == uf_cert else -40
    b = N.banca(linha.get("BANCA"))
    if b and b == certame.banca:
        s += 5
    if certame.cargos and linha.get("CARGO"):
        cargos = {w for c in certame.cargos for w in N.orgao_tokens(c.nome)} - _GENERICOS
        if cargos & N.orgao_tokens(linha.get("CARGO")):
            s += 10
    return max(0.0, min(s, 100.0))


def classificar(certame: Certame, abas: list[Aba], limiar_existente: float = 85, limiar_ambiguo: float = 65) -> Resultado:
    por_certame: dict[tuple, Candidato] = {}
    for aba in abas:
        for n, linha in aba.linhas:
            sc = _score(certame, linha)
            if sc < limiar_ambiguo:
                continue
            chave = (aba.nome, linha.get("COD_INTERNO") or f"linha{n}", N.texto(linha.get("CLIENTE")))
            atual = por_certame.get(chave)
            if atual is None or sc > atual.score:
                por_certame[chave] = Candidato(aba.nome, n, linha.get("COD_INTERNO"), linha.get("CLIENTE") or "",
                                               linha.get("BANCA"), linha.get("SITUACAO"), round(sc, 1))
    cands = sorted(por_certame.values(), key=lambda c: -c.score)[:3]
    if not cands:
        return Resultado("EXTERNO", [])
    if cands[0].score >= limiar_existente:
        # Mesmo órgão pode ter mais de uma demanda no ano (ex.: dois concursos). Se houver mais de um
        # candidato forte com CÓD diferente, não decide sozinho.
        fortes = [c for c in cands if c.score >= limiar_existente]
        cods = {c.cod_interno for c in fortes}
        return Resultado("JA_NA_PLANILHA" if len(cods) == 1 else "AMBIGUO", cands)
    return Resultado("AMBIGUO", cands)
