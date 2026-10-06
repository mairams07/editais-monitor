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
    pad = rf"(?:taxa|valor)\s+d[ae]\s+(?:taxa\s+de\s+)?inscri[cç][aã]o[^\n]{{0,120}}?({DINHEIRO})"
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
    m = re.fullmatch(r"\s*(\d{1,3}(?:\.\d{3})+|\d{1,6})\s*(?:\(.*\))?\s*\**\s*", str(v))
    return int(m.group(1).replace(".", "")) if m else None


# ====================================================================== extração estruturada de edital
# Regras observadas em editais de abertura (Cebraspe, 2026) e escritas para servir às demais bancas.

_ORGAO_INICIO = (r"(?:Secretaria|Pol[íi]cia|Tribunal|C[âa]mara|Prefeitura|Ag[êe]ncia|Advocacia|Minist[ée]rio|Instituto|"
                 r"Universidade|Funda[çc][ãa]o|Departamento|Procuradoria|Controladoria|Corpo de Bombeiros|Companhia|"
                 r"Empresa|Conselho|Defensoria|Assembleia|Servi[çc]o|Superintend[êe]ncia|Escola|Hospital|Autarquia|"
                 r"Banco|Caixa|Munic[íi]pio|Governo|Comando|Ag[êe]ncia|Unidade|Centro|Junta|Receita|Per[íi]cia|"
                 r"Diretoria|Gabinete|Coordenadoria|Fundo|Consórcio|Senado|Infra)")


def _texto_todo(paginas: list[Pagina], n: int | None = None) -> str:
    return "\n".join(p.texto for p in (paginas[:n] if n else paginas))


def _pagina_de(paginas: list[Pagina], trecho_busca: str) -> int | None:
    for p in paginas:
        if trecho_busca[:40] in p.texto:
            return p.numero
    return None


def orgao_do_edital(paginas: list[Pagina], doc: str, url: str) -> tuple[str | None, Evidencia | None]:
    """Órgão para quem o concurso é feito. 1º: sigla do 'EDITAL Nº 1 – SIGLA, DE …' resolvida pelo nome por extenso
    seguido de '(SIGLA)'; 2º: menção 'cargo(s) … da/do <Órgão> (SIGLA)'; 3º: linha de cabeçalho da 1ª página."""
    t = _texto_todo(paginas, 4)
    m = re.search(r"EDITAL\s+N[º°o.]*\s*\d+\s*[–-]\s*([A-ZÀ-Ú0-9][A-ZÀ-Ú0-9/ .-]{1,25}?)\s*,\s*DE\s", t)
    siglas = []
    if m:
        sig = m.group(1).strip()
        siglas = [sig, sig.replace("/", ""), sig.replace("/", "-"), re.sub(r"(\w+)/(\w{2})$", r"\1-\2", sig)]
    for sig in dict.fromkeys(siglas):
        for mm in re.finditer(rf"({_ORGAO_INICIO}[^()\n]{{3,140}}?(?:\n[^()\n]{{1,80}}?)?)\s*\(\s*{re.escape(sig)}\s*\)", t, re.I):
            nome = " ".join(mm.group(1).split())
            nome = re.sub(r"^.*\b(no âmbito d[aoe]s?|todos d[aoe]s?|quadro de pessoal d[aoe]s?)\s+", "", nome, flags=re.I)
            ev = Evidencia(nome.upper(), "CONFIRMADO", doc, _pagina_de(paginas, mm.group(0)), trecho(t, mm.start(), mm.end()), url)
            return nome.upper(), ev
    # "Quadro de Servidores da <Órgão>", "no âmbito da <Órgão>", "cargos efetivos da <Órgão>"
    plano = " ".join(t.split())
    mm = re.search(rf"(?:quadro (?:geral )?(?:de )?(?:servidores|pessoal)(?: efetivo)?|no [âa]mbito|cargos? (?:efetivos? )?(?:vagos )?)"
                   rf"\s+d[aoe]s?\s+({_ORGAO_INICIO}[^,.;()]{{3,200}}?)(?=\s*[,.;(]|\s+o qual|\s+mediante|\s+e\s|\s+nos termos|\s+conforme)",
                   plano, re.I)
    if mm:
        nome = " ".join(mm.group(1).split())
        return nome.upper(), Evidencia(nome.upper(), "CONFIRMADO", doc, _pagina_de(paginas, mm.group(0)[:40]),
                                       trecho(plano, mm.start(), mm.end()), url)
    # cabeçalho: linhas em caixa alta logo antes da linha "EDITAL …", com palavra de órgão
    for p in paginas[:3]:
        linhas = p.texto.splitlines()
        for i, l in enumerate(linhas):
            if not re.match(r"\s*EDITAL\b", l):
                continue
            cab = [re.sub(r"^D[AOE]S?\s+", "", x.strip()) for x in linhas[max(0, i - 6):i]]
            cab = [x for x in cab
                   if x.isupper() and re.match(_ORGAO_INICIO, x, re.I)
                   and not re.search(r"CEBRASPE|CARLOS CHAGAS|VUNESP|CESGRANRIO|IDECAN|AOCP|IBFC|CONCURSO|^GOVERNO|^ESTADO D", x)]
            if cab:
                nome = re.sub(r"\s*(?:[–-]\s*[A-Z/]{2,12}|\([^)]*\))\s*$", "", cab[-1]).strip()
                return nome, Evidencia(nome, "CONFIRMADO", doc, p.numero, cab[-1], url)
    return None, None


_MINUSC = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "para", "com"}


def _titulo(s: str) -> str:
    """'AGENTE DE POLÍCIA' → 'Agente de Polícia' (só quando vem todo em caixa alta)."""
    s = " ".join(s.split()).strip(" .;:–-")
    if not s.isupper():
        return s
    out = []
    for i, w in enumerate(s.lower().split()):
        out.append(w if (i and w in _MINUSC) else (w.upper() if re.fullmatch(r"[ivx]+", w) else w.capitalize()))
    return " ".join(out)


def _nivel_de(txt: str) -> str | None:
    t = N.texto(txt)
    if re.search(r"NIVEL SUPERIOR|ENSINO SUPERIOR|GRADUACAO|BACHAREL|LICENCIATURA|DIPLOMA.{0,80}SUPERIOR|CURSO SUPERIOR", t):
        return "Superior"
    if re.search(r"TECNICO|CURSO TECNICO", t):
        return "Técnico"
    if re.search(r"NIVEL MEDIO|ENSINO MEDIO", t):
        return "Médio"
    if re.search(r"FUNDAMENTAL", t):
        return "Fundamental"
    return None


_SAL = r"(?:REMUNERA[ÇC][ÃA]O|SUBS[ÍI]DIO|VENCIMENTO(?:\s+B[ÁA]SICO)?|BOLSA(?:[- ]AUX[ÍI]LIO)?|SAL[ÁA]RIO)"


def cargos_blocos(paginas: list[Pagina], doc: str, url: str) -> list[dict]:
    """Blocos 'CARGO n: NOME' com REQUISITO e REMUNERAÇÃO/SUBSÍDIO (padrão Cebraspe).
    Sem blocos numerados, tenta um único cargo: '2.1 NOME … REMUNERAÇÃO: R$'."""
    t = _texto_todo(paginas)
    achados = []
    vistos = set()
    pos = [(m.start(), m) for m in re.finditer(r"(?m)^\s*(?:\d+(?:\.\d+)*\s+)?CARGO\s+(\d+)\s*:\s*([^\n]+)", t)]
    for i, (ini, m) in enumerate(pos):
        num = m.group(1)
        fim = pos[i + 1][0] if i + 1 < len(pos) else ini + 6000
        bloco = t[ini:min(fim, ini + 6000)]
        sal = re.search(_SAL + r"[^\n]{0,140}?(R\$\s*[\d.]+,\d{2})", bloco, re.I)
        if num in vistos or not sal:
            continue                       # 2ª menção (ex.: quadro de vagas) ou bloco sem remuneração
        vistos.add(num)
        nome = m.group(2)
        esp = ""
        partes = re.split(r"\s+[–-]\s+(?=(?:[ÁA]REA|ESPECIALIDADE)\b)", nome, maxsplit=1)
        if len(partes) == 2:
            nome, esp = partes[0], re.sub(r"^(?:[ÁA]REA|ESPECIALIDADE)\s*:?\s*", "", partes[1], flags=re.I)
        req = re.search(r"REQUISITOS?[^:]{0,150}:(.{0,600})", bloco, re.I | re.S)
        reg = {"nome": _titulo(nome), "especialidade": _titulo(esp), "num": num}
        tr = trecho(bloco, sal.start(), sal.end())
        reg["SALARIO"] = Evidencia(N.dinheiro(sal.group(1)), "CONFIRMADO", doc, _pagina_de(paginas, bloco[sal.start():sal.end()]) or _pagina_de(paginas, m.group(0)), tr, url)
        niv = _nivel_de(req.group(1)) if req else None
        if niv:
            reg["NIVEL"] = Evidencia(niv, "CONFIRMADO", doc, _pagina_de(paginas, m.group(0)), trecho(bloco, req.start(), min(req.end(), req.start() + 200)), url)
        achados.append(reg)
    if achados:
        return achados
    # cargo único: vencimento-base tem prioridade sobre remuneração total
    sal = (re.search(r"VENCIMENTO[^\n]{0,60}?(R\$\s*[\d.]+,\d{2})", t, re.I)
           or re.search(_SAL + r"[^\n]{0,60}?(R\$\s*[\d.]+,\d{2})", t, re.I))
    frase = re.search(r"vagas?\s+(?:para|no)\s+o\s+cargo\s+de\s+([A-ZÀ-Ú][^,.;\n]{3,120}?)(?=\s*[,.;]|\s+do\s+quadro|\s+o\s+qual|\s+da\s+carreira)",
                      " ".join(t[:20000].split()), re.I)
    if sal and frase:
        reg = {"nome": _titulo(frase.group(1)), "especialidade": "", "num": "1",
               "SALARIO": Evidencia(N.dinheiro(sal.group(1)), "CONFIRMADO", doc, _pagina_de(paginas, sal.group(0)),
                                    trecho(t, sal.start(), sal.end()), url)}
        niv = _nivel_de(t[:30000]) if re.search(r"REQUISITO|ESCOLARIDADE", t[:30000], re.I) else None
        return [reg]
    if sal:
        antes = t[max(0, sal.start() - 6000):sal.start()]
        cand = (re.findall(r"(?m)^\s*\d+(?:\.\d+)*\s+DOS?\s+CARGOS?\s+(?:DE\s+)?([A-ZÀ-Ú][A-ZÀ-Ú ()/–-]{4,120})$", antes)
                or re.findall(r"(?m)^\s*\d+\.\d+\s+CARGO\s*:\s*([A-ZÀ-Ú][A-ZÀ-Ú ()/–-]{4,120})$", antes))
        if cand:
            req = re.search(r"REQUISITOS?\s*:(.{0,600})", antes, re.I | re.S)
            reg = {"nome": _titulo(re.sub(r"\s*\([A-Z]+\)\s*$", "", cand[-1])), "especialidade": "", "num": "1",
                   "SALARIO": Evidencia(N.dinheiro(sal.group(1)), "CONFIRMADO", doc, _pagina_de(paginas, sal.group(0)),
                                        trecho(t, sal.start(), sal.end()), url)}
            niv = _nivel_de(req.group(1)) if req else None
            if niv:
                reg["NIVEL"] = Evidencia(niv, "CONFIRMADO", doc, _pagina_de(paginas, sal.group(0)), " ".join(req.group(1).split()[:30]), url)
            return [reg]
    # cargos do anexo de atribuições ("O cargo de X possui como atribuições"); valores por bloco de escolaridade
    nomes = list(dict.fromkeys(" ".join(m.group(1).split()) for m in
                               re.finditer(r"O cargo de ([^,\n]{3,100}?) (?:possui|tem|compreende|dever[áa]|exerce)", t)))
    if nomes:
        blocos = _blocos_escolaridade(paginas, doc, url)
        out = []
        for n in nomes:
            partes = re.split(r"\s+[–-]\s+", n, maxsplit=1)
            reg = {"nome": _titulo(partes[0]), "especialidade": _titulo(partes[1]) if len(partes) > 1 else "", "num": ""}
            b = _bloco_do_cargo(blocos, partes[0])
            if b:
                for col in ("SALARIO", "TAXA", "NIVEL"):
                    if b.get(col):
                        reg[col] = b[col]
            out.append(reg)
        return out
    return []


def _blocos_escolaridade(paginas: list[Pagina], doc: str, url: str) -> list[dict]:
    """Blocos 'Ensino X Completo / Vencimento inicial: R$ / Valor da Inscrição: R$' (padrão FCC em Diário Oficial)."""
    out = []
    for p in paginas[:12]:
        for m in re.finditer(r"(Ensino (?:Fundamental|M[ée]dio|Superior)(?: Completo)?|N[íi]vel (?:Fundamental|M[ée]dio|T[ée]cnico|Superior))\s*\n"
                             r"(?:.*\n){0,2}?.*?(?:Vencimento|Remunera[çc][ãa]o|Sal[áa]rio)[^\n]{0,40}?(R\$\s*[\d.]+,\d{2})"
                             r"(?:.*\n){0,4}?.*?(?:Valor da Inscri[çc][ãa]o|Taxa de inscri[çc][ãa]o)[^\n]{0,20}?(R\$\s*[\d.]+,\d{2})", p.texto, re.I):
            tr = trecho(p.texto, m.start(), m.end())
            out.append({"pos": (p.numero, m.start()), "fim": None, "texto_pagina": p.numero,
                        "NIVEL": Evidencia(_nivel_de(m.group(1)), "INDÍCIO", doc, p.numero, tr, url),
                        "SALARIO": Evidencia(N.dinheiro(m.group(2)), "INDÍCIO", doc, p.numero, tr, url),
                        "TAXA": Evidencia(N.dinheiro(m.group(3)), "INDÍCIO", doc, p.numero, tr, url),
                        "ini": m.end()})
    # o texto de cada bloco vai até o início do próximo (até 2 páginas adiante)
    for i, b in enumerate(out):
        prox = out[i + 1] if i + 1 < len(out) else None
        partes = []
        for pg in paginas:
            if pg.numero < b["pos"][0] or pg.numero > b["pos"][0] + 2:
                continue
            ini = b["ini"] if pg.numero == b["pos"][0] else 0
            if prox and pg.numero == prox["pos"][0]:
                partes.append(pg.texto[ini:prox["pos"][1]])
                break
            if prox and pg.numero > prox["pos"][0]:
                break
            partes.append(pg.texto[ini:])
        b["texto"] = N.texto(" ".join(partes))
    return out


def _bloco_do_cargo(blocos: list[dict], nome: str) -> dict | None:
    """Bloco cujo quadro de vagas cita o cargo (pela 1ª palavra do nome). Só devolve se for exatamente um."""
    if not blocos:
        return None
    chave = N.texto(nome).split()[0] if N.texto(nome) else ""
    achados = [b for b in blocos if chave and re.search(rf"\b{chave}", b["texto"])]
    return achados[0] if len(achados) == 1 else None


def _rotulos(tab: list[list]) -> tuple[list[str], int]:
    """Rótulo de cada coluna juntando as linhas de cabeçalho (células mescladas = None herdam da esquerda)."""
    n = max(len(r) for r in tab)
    rot = [""] * n
    i = 0
    while i < len(tab) and not any(_int(c) is not None for c in tab[i][1:]):
        ult = ""
        for j in range(n):
            c = tab[i][j] if j < len(tab[i]) else None
            ult = N.texto(c) if c not in (None, "") else (ult if i == 0 else "")
            rot[j] = (rot[j] + " " + ult).strip()
        i += 1
    return rot, i


def vagas_por_cargo(paginas: list[Pagina], doc: str, url: str, nomes: list[str]) -> dict:
    """{texto(nome) | '*': {'VAGAS': ev, 'VAGAS_CR': ev}} a partir dos quadros de vagas."""
    out: dict = {}
    for p in paginas:
        for tab in p.tabelas:
            if not tab or len(tab) < 2:
                continue
            rot, ini = _rotulos(tab)
            if not any("TOTAL" in r or "AC" in r.split() or "AMPLA" in r for r in rot):
                continue
            if re.search(r"CLASSIFICAD|HABILITAD|CONVOCAD|APROVAD", N.texto(" ".join(str(c) for r in tab for c in r if c))):
                continue                     # quadro de classificados/convocados, não de vagas
            tot_im = [j for j, r in enumerate(rot) if "TOTAL" in r and not re.search(r"CADASTRO|RESERVA \(|INCLUIDAS", r)]
            tot_cr = [j for j, r in enumerate(rot) if "TOTAL" in r and "CADASTRO" in r]
            res_im = [j for j, r in enumerate(rot) if re.search(r"\b(AC|AMPLA|PCD|DEFICIEN\w*|PPP|PPIQ|PI|PQ|NEGR\w*|PRET\w*|INDIGEN\w*|QUILOMBOL\w*|TRANS)\b", r)
                      and "CADASTRO" not in r]
            for row in tab[ini:]:
                rotulo = next((str(c) for c in row if c and _int(c) is None), "")
                if N.texto(rotulo).startswith("TOTAL"):
                    continue
                total = _int(row[tot_im[0]]) if tot_im and tot_im[0] < len(row) else None
                partes = [_int(row[j]) for j in res_im if j < len(row) and (not tot_im or j < tot_im[0])]
                soma = sum(x for x in partes if x is not None) if partes and any(x is not None for x in partes) else None
                if total is None and soma is None:
                    continue
                k = _casar_nome(rotulo, nomes) or ("*" if not rotulo or len(nomes) <= 1 else None)
                if k is None:
                    continue
                tr = " | ".join(str(c or "") for c in row)[:200]
                reg = {}
                if total is not None and soma is not None and total != soma:
                    reg["VAGAS"] = Evidencia(None, "INCONSISTÊNCIA", doc, p.numero, f"INCONSISTÊNCIA NO EDITAL: soma {soma} ≠ total {total} · {tr}", url)
                else:
                    reg["VAGAS"] = Evidencia(total if total is not None else soma, "CONFIRMADO", doc, p.numero, tr, url)
                if tot_cr and tot_cr[0] < len(row) and _int(row[tot_cr[0]]) is not None:
                    reg["VAGAS_CR"] = Evidencia(_int(row[tot_cr[0]]), "CONFIRMADO", doc, p.numero, tr, url)
                out.setdefault(k, reg)
    return out


def _casar_nome(rotulo: str, nomes: list[str]) -> str | None:
    r = N.texto(re.sub(r"-\s+", "", re.sub(r"^\s*CARGO\s+\d+\s*:\s*", "", rotulo, flags=re.I)))
    if not r:
        return None
    for n in nomes:
        tn = N.texto(n)
        if tn and (tn in r or r in tn):
            return tn
    return None


def taxas_por_cargo(paginas: list[Pagina], doc: str, url: str, nomes: list[str]) -> dict:
    """{texto(nome) | '*': ev}. Lê 'TAXA(S) [DE INSCRIÇÃO]:' seguida de valor único ou de lista por cargo."""
    out: dict = {}
    for p in paginas:
        for m in re.finditer(r"TAXAS?(?:\s+DE\s+INSCRI[ÇC][ÃA]O)?\s*:", p.texto, re.I):
            jan = p.texto[m.end():m.end() + 700]
            unico = re.match(r"\s*(R\$\s*[\d.]+,\d{2})", jan)
            if unico:
                out["*"] = Evidencia(N.dinheiro(unico.group(1)), "CONFIRMADO", doc, p.numero, trecho(p.texto, m.start(), m.end() + unico.end()), url)
                return out
            for mm in re.finditer(r"(?m)^\s*[a-z]\)\s*([^:\n]+?)\s*:\s*(R\$\s*[\d.]+,\d{2})", jan):
                k = _casar_nome(mm.group(1), nomes)
                if k:
                    out[k] = Evidencia(N.dinheiro(mm.group(2)), "CONFIRMADO", doc, p.numero, " ".join(mm.group(0).split()), url)
            if out:
                return out
    ts = taxa(paginas, doc, url)
    if ts and len({t.valor for t in ts}) == 1:
        out["*"] = ts[0]
    return out


_FASES = [
    (r"prova[s]?\s+objetiva", "Prova Objetiva"),
    (r"prova[s]?\s+discursiva|reda[çc][ãa]o", "Prova Discursiva"),
    (r"prova[s]?\s+pr[áa]tica|teste\s+pr[áa]tico", "Prova Prática"),
    (r"prova[s]?\s+oral", "Prova Oral"),
    (r"capacidade\s+f[íi]sica|aptid[ãa]o\s+f[íi]sica|\bTAF\b|teste\s+f[íi]sico", "Teste de Aptidão Física"),
    (r"exames?\s+m[ée]dicos?|avalia[çc][ãa]o\s+(?:m[ée]dica|de\s+sa[úu]de)|inspe[çc][ãa]o\s+de\s+sa[úu]de", "Exames Médicos"),
    (r"avalia[çc][ãa]o\s+psicol[óo]gica|exame\s+psicot[ée]cnico", "Avaliação Psicológica"),
    (r"investiga[çc][ãa]o\s+social|sindic[âa]ncia", "Investigação Social"),
    (r"curso\s+de\s+forma[çc][ãa]o", "Curso de Formação"),
    (r"t[íi]tulos", "Prova de Títulos"),
    (r"experi[êe]ncia\s+profissional", "Avaliação de Experiência Profissional"),
    (r"heteroidentifica", "Heteroidentificação"),
    (r"per[íi]cia\s+m[ée]dica|biopsicossocial", "Perícia Médica"),
]


def _classificar_fase(txt: str) -> str | None:
    for pad, nome in _FASES:
        if re.search(pad, txt, re.I):
            return nome
    return None


def etapas(paginas: list[Pagina], doc: str, url: str, nomes_cargos: list[str] | None = None) -> tuple[Evidencia | None, dict]:
    """Fases na ordem do edital. Devolve (etapas comuns, {texto(cargo): etapas daquele cargo}).

    Lê os itens 'a) … b) …' da seção que enumera as fases e as etapas seguintes ('A segunda etapa … curso de
    formação'). Item 'apenas para o cargo de X' vale só para X. Sem itens, classifica a frase da própria seção.
    Heteroidentificação e perícia só entram quando aparecem nessa enumeração (o edital as trata como etapa)."""
    nomes_cargos = nomes_cargos or []
    for idx, p in enumerate(paginas[:6]):
        m = re.search(r"(?:compreender[áa]|ser[áa]\s+compost[oa]|compost[oa]\s+de|constar[áa]|consistir[áa])[^.]{0,80}?"
                      r"(?:(?:seguintes\s+)?(?:fases|etapas)[^:\n]{0,50}:|exame\s+de\s+habilidades|provas?\s+objetivas?)", p.texto, re.I)
        if not m:
            continue
        resto = p.texto[m.start():] + ("\n" + paginas[idx + 1].texto if idx + 1 < len(paginas) else "")
        num = re.findall(r"(?m)^\s*(\d+(?:\.\d+)*)\s", p.texto[:m.start()])
        pref = num[-1] if num else None
        corte = None
        for mm in re.finditer(r"(?m)^\s*(\d+\.\d+(?:\.\d+)*)\s", resto[1:]):
            if not pref or not mm.group(1).startswith(pref + "."):
                corte = mm.start() + 1
                break
        jan = resto[:corte if corte else 2500]
        itens = re.findall(r"(?ms)^\s*[a-z]\)\s*(.+?)(?=^\s*[a-z]\)|^\s*\d+\.\d|\Z)", jan)
        itens += re.findall(r"(?mi)^\s*\d+(?:\.\d+)+\s+A\s+(?:segunda|terceira|quarta)\s+etapa(.+?)(?:\.|$)", jan)
        if not itens:
            itens = [" ".join(jan.split())]
            ordem = sorted(((mm.start(), nome) for pad, nome in _FASES for mm in [re.search(pad, itens[0], re.I)] if mm))
            comuns = list(dict.fromkeys(n for _, n in ordem))
            por_cargo: dict = {}
        else:
            comuns, por_cargo = [], {}
            for it in itens:
                nome = _classificar_fase(it)
                if not nome:
                    continue
                so = re.search(r"apenas\s+para\s+(?:o|os)\s+cargos?\s+de\s+([^,;]+)", it, re.I)
                alvos = [k for k in (N.texto(n) for n in nomes_cargos) if so and k and k in N.texto(so.group(1))]
                if alvos:
                    for k in alvos:
                        por_cargo.setdefault(k, []).append((len(comuns), nome))
                elif nome not in comuns:
                    comuns.append(nome)
        if not comuns:
            continue
        tr = trecho(p.texto, m.start(), m.end() + 120)
        ev = Evidencia(", ".join(comuns), "CONFIRMADO", doc, p.numero, tr, url)
        evs = {}
        for k, extras in por_cargo.items():
            lista = list(comuns)
            for pos, nome in sorted(extras, reverse=True):
                lista.insert(pos, nome)
            evs[k] = Evidencia(", ".join(dict.fromkeys(lista)), "CONFIRMADO", doc, p.numero, tr, url)
        return ev, evs
    return None, {}


def cidades(paginas: list[Pagina], doc: str, url: str) -> Evidencia | None:
    """Cidades de aplicação da prova objetiva."""
    for p in paginas:
        m = re.search(r"(?:provas?|objetivas?)[^.]{0,400}?(?:ser[ãa]o|ser[áa])\s+(?:realizad|aplicad)[oa]s?\s+n[oa]s?\s+"
                      r"(?:munic[íi]pios?|cidades?|localidades?)\s+de\s+(.{3,300})", p.texto, re.I | re.S)
        if not m:
            continue
        lista = " ".join(m.group(1).split())
        lista = re.split(r"\.(?:\s|$)|;", lista)[0]
        lista = re.split(r",\s*(?:no|do|com|sendo|em)\b|\s+no\s+Estado|\s+com\s|\s*\(", lista)[0]
        bruto = re.split(r",|\s+e\s+", lista)
        nomes = [re.sub(r"\s*[/–-]\s*[A-Z]{2}\b.*$", "", c).strip() for c in bruto]
        nomes = [re.sub(r"^(?:de|em|no|na)\s+", "", n) for n in nomes]
        nomes = [n for n in nomes if n and len(n) < 40 and not re.search(r"\d", n)]
        if nomes:
            return Evidencia(", ".join(dict.fromkeys(nomes)), "CONFIRMADO", doc, p.numero, trecho(p.texto, m.start(), m.end()), url)
    return None


def limpar_orgao(nome: str, paginas: list[Pagina]) -> str:
    """Corta lixo do nome do órgão e completa secretaria/controladoria municipal sem o município."""
    n = " ".join(nome.split())
    n = re.split(r"\s+EDITAL\b|\s+CONCURSO\s+P[ÚU]BLICO\b|\s+PROCESSO\s+SELETIVO\b", n, flags=re.I)[0]
    n = re.sub(r"\s+(?:D[AOE]S?|E|EM)$", "", n.strip(" ,;–-"), flags=re.I)
    if re.match(r"(SECRETARIA|CONTROLADORIA|PROCURADORIA)[- ]\S*\s*(MUNICIPAL|GERAL DO MUN)", N.texto(n)) and not re.search(r"\bDE\s+[A-Z]{3,}\s*$", N.texto(n).replace("MUNICIPAL DE ", "")):
        cab = "\n".join(p.texto for p in paginas[:2])
        m = re.search(r"(?:PREFEITURA(?: MUNICIPAL)?|MUNIC[ÍI]PIO)\s+D[EO]\s+([A-ZÀ-Ú][A-ZÀ-Ú ]{2,40}?)(?:\s*[/–-]\s*[A-Z]{2}\b|\n|,|\.)", cab, re.I)
        if m:
            n = f"PREFEITURA DE {m.group(1).strip().upper()} – {n}"
    return n.upper()


def preencher_certame(certame, paginas: list[Pagina], doc: str, url: str, uf_reserva: str = "") -> None:
    """Preenche órgão, UF, cargos e campos do certame a partir do edital de abertura já lido."""
    from modelos import Cargo
    orgao, ev_org = orgao_do_edital(paginas, doc, url)
    if orgao:
        orgao = limpar_orgao(orgao, paginas)
    if orgao:
        certame.orgao = orgao
    cid = cidades(paginas, doc, url)
    uf_cid = re.search(r"/([A-Z]{2})\b", cid.trecho).group(1) if cid and re.search(r"/([A-Z]{2})\b", cid.trecho) else ""
    certame.uf = N.uf_no_texto(certame.orgao) or uf_cid or uf_reserva or ""
    cargos = cargos_blocos(paginas, doc, url)
    nomes = [c["nome"] for c in cargos]
    vagas = vagas_por_cargo(paginas, doc, url, nomes)
    taxas = taxas_por_cargo(paginas, doc, url, nomes)
    for c in cargos:
        cg = Cargo(c["nome"], c.get("especialidade", ""))
        for col in ("SALARIO", "NIVEL", "TAXA"):
            if c.get(col) and c[col].valor is not None:
                cg.campos[col] = c[col]
        k = N.texto(c["nome"])
        cg.campos.update(vagas.get(k) or (vagas.get("*") if len(cargos) == 1 else {}) or {})
        if k in taxas:
            cg.campos["TAXA"] = taxas[k]
        certame.cargos.append(cg)
    if "*" in taxas:
        certame.campos_certame["TAXA"] = taxas["*"]
    ev, ev_cargo = etapas(paginas, doc, url, nomes)
    if ev:
        certame.campos_certame["ETAPAS"] = ev
    for cg in certame.cargos:
        if N.texto(cg.nome) in ev_cargo:
            cg.campos["ETAPAS"] = ev_cargo[N.texto(cg.nome)]
    if cid:
        certame.campos_certame["CIDADES"] = cid
    if certame.uf:
        certame.campos_certame["UF"] = Evidencia(certame.uf, "CONFIRMADO", doc, ev_org.pagina if ev_org else None,
                                                 ev_org.trecho if ev_org else (cid.trecho if cid else ""), url)
    esf = N.esfera(certame.orgao) or ("Estadual" if N.uf_no_texto(certame.orgao) else None)
    if esf:
        certame.campos_certame["ESFERA"] = Evidencia(esf, "INDÍCIO", doc, ev_org.pagina if ev_org else None,
                                                     f"classificação pelo órgão: {certame.orgao}", url)
