"""Regras de extração por campo. Cada função devolve Evidencia (com página e trecho) ou None.

Regras genéricas; os adaptadores podem sobrescrever por banca quando o layout do edital for conhecido.
"""
from __future__ import annotations

import re
from datetime import date

import normalizacao as N
from extracao.pdf import Pagina, trecho
from modelos import Evidencia

DINHEIRO = r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}"


def _primeiro(paginas: list[Pagina], padrao: str, doc: str, url: str, flags=re.I | re.S):
    for p in paginas:
        m = re.search(padrao, p.texto, flags)
        if m:
            return p, m
    return None, None


def taxa(paginas, doc, url) -> list[Evidencia]:
    """Todas as taxas citadas (podem variar por nível). Gratuidade expressa → 0,00."""
    achados = []
    pad = rf"(?:taxa|valor)\s+de\s+inscri[cç][aã]o[^R]{{0,120}}?({DINHEIRO})"
    for p in paginas:
        for m in re.finditer(pad, p.texto, re.I | re.S):
            achados.append(Evidencia(N.dinheiro(m.group(1)), "CONFIRMADO", doc, p.numero,
                                     trecho(p.texto, m.start(), m.end()), url))
    if not achados:
        p, m = _primeiro(paginas, r"inscri[cç][aã]o\s+(?:ser[aá]\s+)?gratuita|isento\s+de\s+taxa|sem\s+cobran[cç]a\s+de\s+taxa", doc, url)
        if m:
            achados.append(Evidencia(N.dinheiro("gratuita"), "CONFIRMADO", doc, p.numero,
                                     trecho(p.texto, m.start(), m.end()), url))
    return achados


_ETAPAS = [
    (r"prova\s+objetiva", "Prova Objetiva"),
    (r"prova\s+discursiva|reda[cç][aã]o", "Prova Discursiva"),
    (r"prova\s+pr[aá]tica", "Prova Prática"),
    (r"prova\s+oral", "Prova Oral"),
    (r"teste\s+de\s+aptid[aã]o\s+f[ií]sica|TAF\b|prova\s+de\s+capacidade\s+f[ií]sica", "Teste de Aptidão Física"),
    (r"avalia[cç][aã]o\s+psicol[oó]gica|exame\s+psicot[eé]cnico", "Avaliação Psicológica"),
    (r"investiga[cç][aã]o\s+social|sindic[aâ]ncia\s+de\s+vida", "Investigação Social"),
    (r"curso\s+de\s+forma[cç][aã]o", "Curso de Formação"),
    (r"(?:prova|avalia[cç][aã]o)\s+de\s+t[ií]tulos", "Prova de Títulos"),
]


def etapas(paginas, doc, url) -> Evidencia | None:
    """Etapas na ordem em que aparecem na seção que as enumera (procura 'constará/compreenderá das seguintes etapas')."""
    p, m = _primeiro(paginas, r"(?:const(?:ar[aá]|ituir[aá])|compreender[aá]|ser[aá]\s+composto)[^.]{0,80}?(?:etapas|fases)[:\s]", doc, url)
    if not m:
        return None
    janela = p.texto[m.end(): m.end() + 1500]
    pos = []
    for pad, nome in _ETAPAS:
        mm = re.search(pad, janela, re.I)
        if mm and nome not in [n for _, n in pos]:
            pos.append((mm.start(), nome))
    if not pos:
        return None
    lista = ", ".join(n for _, n in sorted(pos))
    return Evidencia(lista, "CONFIRMADO", doc, p.numero, trecho(p.texto, m.start(), m.end() + 200), url)


def cidades(paginas, doc, url) -> Evidencia | None:
    """Cidades de aplicação da prova objetiva."""
    p, m = _primeiro(paginas, r"(?:provas?\s+(?:objetivas?\s+)?ser[aã]o\s+(?:aplicadas?|realizadas?)\s+n[ao]s?\s+(?:cidades?|munic[ií]pios?)\s+de)\s+([^.;\n]+(?:\n[^.;\n]+)?)", doc, url)
    if not m:
        return None
    bruto = re.split(r",|\se\s|/", m.group(1))
    nomes = [re.sub(r"\s*[-–]\s*[A-Z]{2}$", "", c.strip()).strip() for c in bruto]
    nomes = [n for n in nomes if n and len(n) < 40]
    if not nomes:
        return None
    return Evidencia(", ".join(nomes), "CONFIRMADO", doc, p.numero, trecho(p.texto, m.start(), m.end()), url)


def data_publicacao(paginas, doc, url) -> date | None:
    meses = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
             "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
    for p in paginas[:2] + paginas[-2:]:
        m = re.search(r"(\d{1,2})\s+de\s+(" + "|".join(meses) + r")\s+de\s+(20\d{2})", p.texto, re.I)
        if m:
            return date(int(m.group(3)), meses[m.group(2).lower()], int(m.group(1)))
    return None


def tabela_cargos(paginas: list[Pagina], doc: str, url: str) -> list[dict]:
    """Lê quadros de vagas/remuneração como tabela. Devolve uma entrada por linha de cargo com evidências.

    Identifica colunas pelo cabeçalho (cargo, especialidade, vagas/ampla/PcD/negros…, CR, remuneração/vencimento,
    escolaridade). Soma ampla + reservas quando o edital separa. Se não houver total, soma; se houver, valida."""
    saida = []
    for p in paginas:
        for tab in p.tabelas:
            if not tab or len(tab) < 2:
                continue
            cab = [N.texto(c) for c in tab[0]]
            idx = _mapear(cab)
            if "CARGO" not in idx or not ({"VAGAS", "RESERVAS", "SALARIO"} & idx.keys()):
                continue
            for linha in tab[1:]:
                cel = lambda k: (linha[idx[k]] if k in idx and idx[k] < len(linha) else None)
                nome = " ".join(str(cel("CARGO") or "").split())
                if not nome or N.texto(nome).startswith("TOTAL"):
                    continue
                nome = re.sub(r"^\s*(?:\d{1,4}|[A-Z]\d{1,3})\s*[-–.]\s*", "", nome)  # remove código do cargo
                reg = {"cargo": nome, "pagina": p.numero, "trecho": " | ".join(str(c or "") for c in linha)[:250]}
                if "ESPECIALIDADE" in idx:
                    reg["especialidade"] = " ".join(str(cel("ESPECIALIDADE") or "").split())
                vagas = [_int(linha[i]) for i in idx.get("RESERVAS", []) if i < len(linha)]
                total = _int(cel("VAGAS"))
                if vagas and any(v is not None for v in vagas):
                    soma = sum(v or 0 for v in vagas)
                    reg["vagas"] = soma
                    if total is not None and total != soma:
                        reg["inconsistencia"] = f"soma {soma} ≠ total {total}"
                elif total is not None:
                    reg["vagas"] = total
                elif re.search(r"\bCR\b|cadastro", str(cel("VAGAS") or ""), re.I):
                    reg["vagas"] = "-"
                cr = cel("VAGAS_CR")
                if cr is not None:
                    reg["vagas_cr"] = _int(cr) if _int(cr) is not None else "CR"
                if "SALARIO" in idx:
                    reg["salario"] = N.dinheiro(cel("SALARIO"))
                if "NIVEL" in idx:
                    reg["nivel"] = N.nivel(cel("NIVEL"))
                saida.append(reg)
    return saida


def _mapear(cab: list[str]) -> dict:
    idx: dict = {}
    for i, c in enumerate(cab):
        if re.search(r"^CARGO|FUNCAO|^EMPREGO", c) and "CARGO" not in idx:
            idx["CARGO"] = i
        elif re.search(r"ESPECIALIDADE|AREA|DISCIPLINA", c):
            idx["ESPECIALIDADE"] = i
        elif re.search(r"CADASTRO|\bCR\b", c):
            idx["VAGAS_CR"] = i
        elif re.search(r"AMPLA|PCD|DEFICIENCIA|NEGR|PRET|INDIGEN|QUILOMBOL|COTA", c):
            idx.setdefault("RESERVAS", []).append(i)
        elif re.search(r"TOTAL|^VAGAS", c):
            idx["VAGAS"] = i
        elif re.search(r"VENCIMENTO|REMUNERACAO|SALARIO|SUBSIDIO|BOLSA", c) and "SALARIO" not in idx:
            idx["SALARIO"] = i
        elif re.search(r"ESCOLARIDADE|REQUISITO|NIVEL", c):
            idx["NIVEL"] = i
    # vencimento-base prevalece sobre remuneração total (que vai só para o LOG)
    venc = [i for i, c in enumerate(cab) if re.search(r"VENCIMENTO|BOLSA|SUBSIDIO", c)]
    if venc:
        idx["SALARIO"] = venc[0]
    return idx


def _int(v):
    if v is None:
        return None
    m = re.fullmatch(r"\s*(\d{1,6})\s*(?:\(.*\))?\s*", str(v))
    return int(m.group(1)) if m else None
