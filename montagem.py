"""Certame extraído → linhas EXTERNO (uma por cargo/especialidade)."""
from __future__ import annotations

import normalizacao as N
from modelos import Certame, Evidencia
from planilha import LinhaNova

# Colunas que vêm do edital, cargo a cargo ou do certame inteiro.
CAMPOS_EDITAL = ["NIVEL", "SALARIO", "VAGAS", "VAGAS_CR", "ETAPAS", "TAXA", "HOMOLOGADAS", "UF", "CIDADES",
                 "VALOR_GLOBAL", "ESFERA"]


class CertameIncompleto(Exception):
    pass


def cliente(certame: Certame) -> str:
    """CLIENTE = nome do órgão como no edital, caixa alta com acento (padrão da planilha). Obrigatório."""
    nome = " ".join((certame.orgao or "").split())
    if not nome:
        raise CertameIncompleto("órgão não identificado no edital — CLIENTE é obrigatório")
    from extracao.campos import cliente_valido
    if not cliente_valido(nome):
        raise CertameIncompleto(f"órgão lido do edital não parece o cliente ('{nome[:60]}') — conferir manualmente")
    return nome.upper()


def linhas(certame: Certame, ano: int, situacao: str = "EXTERNO") -> list[LinhaNova]:
    cli = cliente(certame)
    ev_base = Evidencia(cli, "CONFIRMADO", documento=_doc_edital(certame), url=certame.url,
                        trecho=certame.titulo[:200])
    seg = N.segmento(certame.orgao) or ("Órgão Federal" if N.esfera(certame.orgao) == "Federal" else None)
    esf = certame.campos_certame.get("ESFERA") or (
        Evidencia(N.esfera(certame.orgao), "INDÍCIO", trecho="classificação pelo nome do órgão")
        if N.esfera(certame.orgao) else None)
    chave = f"{N.BANCAS[certame.banca]}:{certame.id_banca}"
    if not certame.cargos:
        raise CertameIncompleto("nenhum cargo extraído do edital")

    saida = []
    for cargo in certame.cargos:
        c: dict[str, tuple[object, Evidencia | None]] = {
            "ANO": (ano, None),
            "BANCA": (N.BANCAS[certame.banca], None),
            "TIPO": (N.TIPOS.get(certame.tipo, "Concurso"), None),
            "CLIENTE": (cli, ev_base),
            # OBJETO: frase do edital; título de matéria ou nome interno da banca nunca entram
            "OBJETO": ((certame.campos_certame["OBJETO"].valor, certame.campos_certame["OBJETO"])
                       if certame.campos_certame.get("OBJETO") else (None, None)),
            "SEGMENTO": (seg, Evidencia(seg, "INDÍCIO", trecho="classificação automática pelo nome do órgão")
                         if seg else None),
            "SITUACAO": (situacao, None),
            "CARGO": (cargo.nome, cargo.campos.get("CARGO")),
            "ESPECIALIDADE": (cargo.especialidade or None, cargo.campos.get("ESPECIALIDADE")),
        }
        for campo in CAMPOS_EDITAL:
            ev = cargo.campos.get(campo) or certame.campos_certame.get(campo)
            if campo == "ESFERA" and ev is None:
                ev = esf
            if ev is not None and ev.status in ("CONFIRMADO", "INDÍCIO") and not N.vazio(ev.valor):
                c[campo] = (ev.valor, ev)
        saida.append(LinhaNova(c, chave))
    return saida


def _doc_edital(certame: Certame) -> str:
    eds = [d for d in certame.documentos if d.tipo == "edital"]
    return eds[0].titulo if eds else ""
