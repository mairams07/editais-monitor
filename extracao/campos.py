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


_BANCA_NOME = re.compile(r"CESGRANRIO|CEBRASPE|CARLOS CHAGAS|VUNESP|IDECAN|\bAOCP\b|\bIBFC\b|\bIBGP\b|GETULIO VARGAS|"
                         r"CONSULPLAN|QUADRIX|FUNDATEC|\bIADES\b|SELECON|FEPESE|\bE O INSTITUTO\b|\bE A FUNDA", re.I)


def orgao_do_edital(paginas: list[Pagina], doc: str, url: str, completas: list[Pagina] | None = None) -> tuple[str | None, Evidencia | None]:
    """Órgão para quem o concurso é feito. 1º: sigla do 'EDITAL Nº 1 – SIGLA, DE …' resolvida pelo nome por extenso
    seguido de '(SIGLA)'; 2º: menção 'cargo(s) … da/do <Órgão> (SIGLA)'; 3º: linha de cabeçalho da 1ª página."""
    t = _texto_todo(paginas, 4)
    m = re.search(r"EDITAL\s+N[º°o.]*\s*\d+\s*[–-]\s*([A-ZÀ-Ú0-9][A-ZÀ-Ú0-9/ .-]{1,25}?)\s*,\s*DE\s", t)
    siglas = []
    if m:
        sig = m.group(1).strip()
        siglas = [sig, sig.replace("/", ""), sig.replace("/", "-"), re.sub(r"(\w+)/(\w{2})$", r"\1-\2", sig)]
    t_sig = _texto_todo(completas, 6) if completas else t   # a sigla pode estar definida antes do recorte (portaria)
    for sig in dict.fromkeys(siglas):
        for mm in re.finditer(rf"({_ORGAO_INICIO}[^()\n]{{3,140}}?(?:\n[^()\n]{{1,80}}?)?)\s*\(\s*{re.escape(sig)}\s*\)", t_sig, re.I):
            nome = " ".join(mm.group(1).split())
            nome = re.sub(r"^.*\b(no âmbito d[aoe]s?|todos d[aoe]s?|quadro de pessoal d[aoe]s?)\s+", "", nome, flags=re.I)
            ev = Evidencia(nome.upper(), "CONFIRMADO", doc, _pagina_de(completas or paginas, mm.group(0)), trecho(t_sig, mm.start(), mm.end()), url)
            return nome.upper(), ev
    # "Quadro de Servidores da <Órgão>", "no âmbito da <Órgão>", "cargos efetivos da <Órgão>"
    plano = " ".join(t.split())
    mm = re.search(rf"(?:quadro (?:geral )?(?:de )?(?:servidores|pessoal)(?: efetivo)?|no [âa]mbito|cargos? (?:efetivos? )?(?:vagos )?)"
                   rf"\s+d[aoe]s?\s+({_ORGAO_INICIO}[^,.;()]{{3,200}}?)(?=\s*[,.;(]|\s+o qual|\s+mediante|\s+e\s|\s+nos termos|\s+conforme)",
                   plano, re.I)
    # "… cargos de X e de Y da Polícia Civil de Pernambuco, mediante …" / "o Delegado-Geral da Polícia Civil da Bahia, no uso"
    if not mm:
        mm = (re.search(rf"\bd[ao]s?\s+({_ORGAO_INICIO}[^,.;()]{{3,120}}?)\s*,\s*(?:mediante|o qual|nos termos|conforme|no uso)", plano[:4000], re.I)
              or re.search(rf"(?:GERAL|SECRET[ÁA]RI[OA][A-ZÀ-Ú() ]*)\s+D[AO]\s+({_ORGAO_INICIO}[^,.;()]{{3,120}}?)\s*,", plano[:4000], re.I))
    if mm and not _BANCA_NOME.search(mm.group(1)):     # "da Fundação Cesgranrio" é a banca, não o cliente
        nome = " ".join(mm.group(1).split())
        return nome.upper(), Evidencia(nome.upper(), "CONFIRMADO", doc, _pagina_de(paginas, mm.group(0)[:40]),
                                       trecho(plano, mm.start(), mm.end()), url)
    # "Petrobras Transporte S.A. (TRANSPETRO) realizará processo seletivo" / "… (SIGLA) torna público"
    mm = re.search(r"([A-ZÀ-Ú][\wÀ-ú .&–-]{3,120}?)\s*\(\s*([A-Z][A-Z0-9/-]{1,15})\s*\)\s*,?\s+(?:realizar[áa]|torna(?:m)?\s+p[úu]blic)",
                   plano[:5000])
    if mm and not _BANCA_NOME.search(mm.group(1)):
        nome = f"{' '.join(mm.group(1).split())} ({mm.group(2)})".upper()
        nome = re.sub(r"^.*\b(?:19|20)\d{2}\s*\.\s+", "", nome)      # sobra do cabeçalho "…, DE 11 DE AGOSTO DE 2026."
        nome = re.sub(r"^(?:A|O)\s+", "", nome)
        return nome, Evidencia(nome, "CONFIRMADO", doc, _pagina_de(paginas, mm.group(0)[:40]), trecho(plano, mm.start(), mm.end()), url)
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
        if not sal and num not in vistos:
            # remuneração dada uma vez para o grupo ("2.1 ANALISTA – TODAS AS ESPECIALIDADES … REMUNERAÇÃO: R$")
            heads = [h.start() for h in re.finditer(r"(?m)^\s*\d+\.\d+\s+(?!\d)", t[:ini])]
            prox = re.search(r"(?m)^\s*\d+\.\d+\s+(?!\d)", t[ini + 1:])
            if heads:
                secao = t[heads[-1]:ini + 1 + (prox.start() if prox else 6000)]
                sal_g = re.search(_SAL + r"[^\n]{0,140}?(R\$\s*[\d.]+,\d{2})", secao, re.I)
                if sal_g:
                    bloco = secao
                    sal = sal_g
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
    quadro = _cargos_quadro(paginas, doc, url)
    if quadro:
        return quadro
    # cargos em itens: "2.5.1 Delegado de Polícia Civil: vencimento básico no valor de R$ 6.449,78"
    itens = list(re.finditer(r"(?m)^\s*\d+(?:\.\d+)+\s+([A-ZÀ-Ú][^:\n]{4,120}):\s*vencimento[^\n]{0,60}?(R\$\s*[\d.]+,\d{2})", t, re.I))
    if itens:
        out = []
        for m in itens:
            for nome in re.split(r"\s+e\s+(?=[A-ZÀ-Ú])", m.group(1)):
                out.append({"nome": _titulo(nome), "especialidade": "", "num": "",
                            "SALARIO": Evidencia(N.dinheiro(m.group(2)), "CONFIRMADO", doc, _pagina_de(paginas, m.group(0).strip()[:40]),
                                                 trecho(t, m.start(), m.end()), url)})
        return out
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
    # último recurso: quadro de vagas com uma linha por cargo
    return _cargos_tabela(paginas, doc, url)


def _cel(c) -> str:
    """Célula limpa: alguns PDFs (ex.: IFPA 2026) trazem um ponto antes de cada valor."""
    return " ".join(str(c or "").split()).strip(" .")


def _junta_letras(s: str) -> str:
    """'Educacionais' extraído como 'Ed u c a c i o n a i s': junta 3+ letras soltas à palavra anterior."""
    toks, out = s.split(), []
    i = 0
    while i < len(toks):
        j = i
        while j < len(toks) and len(toks[j]) == 1 and toks[j].isalpha():
            j += 1
        if j - i >= 3:
            letras = "".join(toks[i:j])
            if out and len(out[-1]) <= 3:
                out[-1] += letras
            else:
                out.append(letras)
            i = j
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)


def _cargos_tabela(paginas: list[Pagina], doc: str, url: str) -> list[dict]:
    """Quadro de vagas com uma linha por cargo (padrão Instituto AOCP, IBFC e outros):
    'Código | Cargo | [Classe] | AC | PcD | PPP… | Total | [CR] | [Taxa] | [Vencimento]'.
    Vencimento pode vir em quadro à parte por classe/nível ('Nível C | R$ 2.607,70')."""
    por_classe: dict[str, tuple] = {}
    for p in paginas:
        for tab in p.tabelas:
            for row in tab:
                cs = [_cel(c) for c in row if _cel(c)]
                if len(cs) == 2 and re.search(r"R\$", cs[1]) and re.search(r"VENCIMENTO|REMUNERA|SALARIO|SUBSIDIO",
                                                                         N.texto(" ".join(_cel(c) for c in tab[0]))):
                    m = re.fullmatch(r"(?:N[ÍI]VEL(?: DE CLASSIFICA[ÇC][ÃA]O)?|CLASSE)?\s*([A-E])", N.texto(cs[0]))
                    if m:
                        por_classe[m.group(1)] = (N.dinheiro(cs[1]), p.numero, " | ".join(cs))
    # cargo único com ênfases ("1. CARGO: PROFISSIONAL TRANSPETRO DE NÍVEL TÉCNICO / REMUNERAÇÃO: salário básico de R$")
    cargo_unico, sal_unico = "", None
    for p in paginas:
        m = re.search(r"(?m)^\s*(?:\d+\.\s*)?CARGO\s*:\s*([^\n]{4,100})\n\s*REMUNERA[ÇC][ÃA]O\s*:[^\n]{0,40}?(R\$\s*[\d.]+,\d{2})", p.texto)
        if m:
            cargo_unico = _titulo(m.group(1).strip())
            sal_unico = Evidencia(N.dinheiro(m.group(2)), "CONFIRMADO", doc, p.numero, " ".join(m.group(0).split()[:30]), url)
            break
    out, vistos = [], set()
    for p in paginas:
        for tab in p.tabelas:
            if not tab or len(tab) < 2:
                continue
            limpa = [[_cel(c) or None for c in r] for r in tab]
            rot, ini = _rotulos(limpa)
            ic = [j for j, r in enumerate(rot) if re.search(r"\b(CARGO|FUNCAO|EMPREGO)S?\b", r) and not re.search(r"\bCOD", r)]
            # quadro por ênfase e polo (Transpetro 2026): ênfase = especialidade do cargo único do edital
            enfase = not ic and [j for j, r in enumerate(rot) if re.search(r"^ENFASES?$|^ENFASE\b", r)]
            if enfase:
                ic = enfase
            if not ic or ini >= len(limpa):
                continue
            ic = ic[0]
            todo = " ".join(rot)
            if sum(1 for r in rot if r.strip() in ("VAGAS", "VAGAS + CADASTRO DE RESERVA")) >= 2:
                continue                     # subcolunhas sem rótulo: colunas desalinhadas no PDF, leitura insegura
            if enfase and re.search(r"VAGAS \+ CADASTRO", todo):
                continue                     # quadro "vagas + cadastro de reserva": não separa vagas imediatas
            if not re.search(r"VAGA|CADASTRO", todo) or re.search(r"CLASSIFICAD|HABILITAD|CONVOCAD|APROVAD|CORRIGID|CORRECAO", todo):
                continue                     # não é quadro de vagas (ex.: quantitativo de provas corrigidas)
            tot = [j for j, r in enumerate(rot) if "TOTAL" in r and "CADASTRO" not in r and j != ic
                   and re.search(r"VAGA|AMPLA|\bAC\b", " ".join(rot))]
            # cotas: palavra inteira ou quebrada no PDF ("QUILOM BOLAS")
            res = [j for j, r in enumerate(rot) if j != ic and "TOTAL" not in r and "CADASTRO" not in r and
                   (re.search(r"\b(AC|PPP?\d?|PPI\d?|PN\d?|PI\d?|PQ\d?)\b", r)
                    or re.search(r"AMPLA|PCD|DEFICIEN|NEGR|PRET|INDIGEN|QUILOMBOL", r.replace(" ", "")))]
            icr = [j for j, r in enumerate(rot) if re.search(r"CADASTRO|\bCR\b", r) and j != ic]
            res = [j for j in res if j not in icr and (not tot or j < tot[0])]   # cotas do grupo "vagas", antes do total
            icr = sorted(icr, key=lambda j: 0 if "TOTAL" in rot[j] else 1)          # total do cadastro, se houver
            isal = [j for j, r in enumerate(rot) if re.search(r"VENCIMENTO|REMUNERA|SALARIO|SUBSIDIO|SOLDO|BOLSA", r)]
            itx = [j for j, r in enumerate(rot) if re.search(r"TAXA|VALOR DA INSCRI", r)]
            icl = [j for j, r in enumerate(rot) if re.search(r"^CLASSE|NIVEL DE CLASSIFICA", r)]
            if not (tot or res or isal):
                continue
            linhas = []
            for row in limpa[ini:]:
                so_nome = row[ic] if ic < len(row) else None
                if so_nome and linhas and not any(c for j, c in enumerate(row) if j != ic):
                    linhas[-1] = list(linhas[-1])
                    linhas[-1][ic] = f"{linhas[-1][ic] or ''} {so_nome}".strip()
                    continue
                linhas.append(row)
            for row in linhas:
                cel = lambda j: (row[j] if j < len(row) else None)
                nome = cel(ic) or ""
                if (not nome or _int(nome) is not None or len(nome) > 90
                        or re.match(r"TOTAL|N[ÍI]VEL\b|EXCETO", N.texto(nome)) or "EXCETO" in N.texto(nome)):
                    continue
                nome = _junta_letras(nome)
                nome = re.sub(r"^\s*(?:\d{1,4}|[A-Z]\d{1,3})\s*[-–.]\s*", "", nome)
                nome = re.sub(r"^(?:CARGO|EMPREGO|FUN[ÇC][ÃA]O)\s*\d+\s*:\s*", "", nome, flags=re.I)
                nome = re.split(r"\s+R\$", nome)[0].strip(" *")
                esp = ""
                m = re.match(r"(.+?)\s*(?:/|[-–])\s*(?:[ÁA]rea|Especialidade)\s*:?\s*(.+)$", nome, re.I)
                if m:
                    nome, esp = m.group(1), m.group(2)
                if enfase:
                    nome, esp = cargo_unico or nome, nome
                chave = _chave(nome, esp)
                if chave in vistos and not enfase:
                    continue
                tr = " ".join(" | ".join(c or "" for c in row).split()[:30])
                reg = {"nome": _titulo(nome) if nome.isupper() else nome, "especialidade": _titulo(esp) if esp.isupper() else esp, "num": ""}
                total = _int(cel(tot[0])) if tot else None
                partes = [_int(cel(j)) for j in res]
                soma = sum(x for x in partes if x is not None) if any(x is not None for x in partes) else None
                cr = cel(icr[0]) if icr else None
                if total is not None and soma is not None and total != soma:
                    # quadro com grupos (vagas + cadastro + total geral) que esta leitura genérica não separa com
                    # segurança: não preenche vagas (nem afirma inconsistência do edital)
                    cr = None
                elif total is not None or soma is not None:
                    reg["VAGAS"] = Evidencia(total if total is not None else soma, "CONFIRMADO", doc, p.numero, tr, url)
                elif re.fullmatch(r"CR|CADASTRO DE RESERVA", N.texto(cel(tot[0]) if tot else "")):
                    reg["VAGAS"] = Evidencia("-", "CONFIRMADO", doc, p.numero, tr, url)
                if cr is not None and _int(cr) is not None:
                    reg["VAGAS_CR"] = Evidencia(_int(cr), "CONFIRMADO", doc, p.numero, tr, url)
                msal = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", cel(isal[0]) or "") if isal else None
                if msal and not re.search(r"\bAT[ÉE]\b", cel(isal[0]) or "", re.I):
                    reg["SALARIO"] = Evidencia(N.dinheiro(msal.group(0)), "CONFIRMADO", doc, p.numero, tr, url)
                elif icl and (cel(icl[0]) or "").upper() in por_classe:
                    v, pg, t2 = por_classe[(cel(icl[0]) or "").upper()]
                    reg["SALARIO"] = Evidencia(v, "CONFIRMADO", doc, pg, " ".join((tr + " · " + t2).split()[:30]), url)
                mtx = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", cel(itx[0]) or "") if itx else None
                if mtx:
                    reg["TAXA"] = Evidencia(N.dinheiro(mtx.group(0)), "CONFIRMADO", doc, p.numero, tr, url)
                if enfase and sal_unico and "SALARIO" not in reg:
                    reg["SALARIO"] = sal_unico
                if enfase and chave in vistos:
                    # mesma ênfase em outro polo de trabalho: soma as vagas
                    ant = next(x for x in out if _chave(x["nome"], x["especialidade"]) == chave)
                    if ant.get("VAGAS") and reg.get("VAGAS") and isinstance(ant["VAGAS"].valor, int) and isinstance(reg["VAGAS"].valor, int):
                        ant["VAGAS"] = Evidencia(ant["VAGAS"].valor + reg["VAGAS"].valor, "CONFIRMADO", doc, p.numero,
                                                 f"soma dos polos de trabalho da ênfase · {tr}"[:250], url)
                    continue
                if len(reg) > 3:
                    vistos.add(chave)
                    out.append(reg)
    return out


def _cargos_quadro(paginas: list[Pagina], doc: str, url: str) -> list[dict]:
    """Cargo como título em maiúsculas seguido do quadro 'Escolaridade | Ampla Concorrência | PcD | Total | Subsídio'
    (padrão Cesgranrio, ex.: PC-AP 2026). A linha de dados traz 'AC PcD Total R$ valor'."""
    out = []
    for p in paginas[:12]:
        t = p.texto
        heads = list(re.finditer(r"(?m)^([A-ZÀ-Ú][A-ZÀ-Ú ()/–-]{4,100})\n(?=(?:[^\n]*\n){0,6}?[^\n]*(?:Subs[íi]dio|Remunera[çc][ãa]o|Vencimento))", t))
        for i, h in enumerate(heads):
            fim = heads[i + 1].start() if i + 1 < len(heads) else min(len(t), h.end() + 2500)
            bloco = t[h.end():fim]
            cab = bloco[:400]
            # título genérico ou quadro com coluna "Cargo"/"Área" (vários cargos por quadro): não é este padrão
            if (re.match(r"(?:QUADRO|CARGOS?\b|ANEXO|TABELA|MUNIC|ESTADO|PREFEITURA|SECRETARIA)", h.group(1))
                    or re.search(r"(?m)^\s*(?:Cargo|[ÁA]rea de Atua[çc][ãa]o)\b", cab)
                    or not re.search(r"Ampla|Vagas|Cadastro", cab, re.I)):
                continue
            lin = re.search(r"(?m)((?:\d+\s+){2,5})(R\$\s*[\d.]+,\d{2})", bloco)
            if not lin:
                continue
            nums = [int(x) for x in lin.group(1).split()]
            tr = " ".join((h.group(1).strip() + " … " + " ".join(lin.group(0).split())).split()[:30])
            reg = {"nome": _titulo(h.group(1).strip()), "especialidade": "", "num": str(len(out) + 1),
                   "SALARIO": Evidencia(N.dinheiro(lin.group(2)), "CONFIRMADO", doc, p.numero, tr, url)}
            so_cr = re.search(r"Cadastro\s+de\s*\n?.*?Reserva", cab, re.I | re.S) and not re.search(r"\bVagas\b", cab, re.I)
            total = nums[-1] if len(nums) >= 2 else None
            soma = sum(nums[:-1]) if len(nums) >= 2 else None
            if total is not None:
                if soma != total:
                    reg["VAGAS"] = Evidencia(None, "INCONSISTÊNCIA", doc, p.numero, f"INCONSISTÊNCIA NO EDITAL: soma {soma} ≠ total {total} · {tr}", url)
                elif so_cr:
                    reg["VAGAS"] = Evidencia("-", "CONFIRMADO", doc, p.numero, tr, url)
                    reg["VAGAS_CR"] = Evidencia(total, "CONFIRMADO", doc, p.numero, tr, url)
                else:
                    reg["VAGAS"] = Evidencia(total, "CONFIRMADO", doc, p.numero, tr, url)
            niv = _nivel_de(bloco[:lin.end() + 400])
            if niv:
                reg["NIVEL"] = Evidencia(niv, "CONFIRMADO", doc, p.numero, trecho(bloco, 0, min(len(bloco), lin.end())), url)
            out.append(reg)
    return out


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
            if not any("VAGA" in r or "CADASTRO" in r for r in rot):
                continue                     # quadro sem "vagas" no cabeçalho (ex.: quantitativos de correção de provas)
            if re.search(r"CLASSIFICAD|HABILITAD|CONVOCAD|APROVAD", N.texto(" ".join(str(c) for r in tab for c in r if c))):
                continue                     # quadro de classificados/convocados, não de vagas
            tot_im = [j for j, r in enumerate(rot) if "TOTAL" in r and not re.search(r"CADASTRO|RESERVA \(|INCLUIDAS", r)]
            tot_cr = [j for j, r in enumerate(rot) if "TOTAL" in r and "CADASTRO" in r]
            res_im = [j for j, r in enumerate(rot) if re.search(r"\b(AC|AMPLA|PCD|DEFICIEN\w*|PP|PPP|PPIQ|PI|PQ|NEGR\w*|PRET\w*|INDIGEN\w*|QUILOMBOL\w*|TRANS)\b", r)
                      and "CADASTRO" not in r]
            for row in tab[ini:]:
                rotulo = next((str(c) for c in row if c and _int(c) is None), "")
                if N.texto(rotulo).startswith("TOTAL"):
                    continue
                total = _int(row[tot_im[0]]) if tot_im and tot_im[0] < len(row) else None
                partes = [_int(row[j]) for j in res_im if j < len(row) and (not tot_im or j < tot_im[0])]
                soma = sum(x for x in partes if x is not None) if partes and any(x is not None for x in partes) else None
                so_cr = tot_im and tot_im[0] < len(row) and re.fullmatch(r"\s*CR\s*", str(row[tot_im[0]] or ""))
                if total is None and soma is None and not so_cr:
                    continue
                k = _casar_nome(rotulo, nomes) or ("*" if not rotulo or len(nomes) <= 1 else None)
                if k is None:
                    continue
                tr = " | ".join(str(c or "") for c in row)[:200]
                reg = {}
                if so_cr:
                    reg["VAGAS"] = Evidencia("-", "CONFIRMADO", doc, p.numero, tr, url)
                elif total is not None and soma is not None and total != soma:
                    reg["VAGAS"] = Evidencia(None, "INCONSISTÊNCIA", doc, p.numero, f"INCONSISTÊNCIA NO EDITAL: soma {soma} ≠ total {total} · {tr}", url)
                else:
                    reg["VAGAS"] = Evidencia(total if total is not None else soma, "CONFIRMADO", doc, p.numero, tr, url)
                if tot_cr and tot_cr[0] < len(row) and _int(row[tot_cr[0]]) is not None:
                    reg["VAGAS_CR"] = Evidencia(_int(row[tot_cr[0]]), "CONFIRMADO", doc, p.numero, tr, url)
                out.setdefault(k, reg)
    return out


def _chave(nome: str, esp: str = "") -> str:
    return N.texto(nome) + ("|" + N.texto(esp) if esp else "")


def _casar_nome(rotulo: str, nomes: list) -> str | None:
    """nomes: str ou (cargo, especialidade). Com especialidade, as duas partes precisam aparecer no rótulo."""
    r = N.texto(re.sub(r"-\s+", "", re.sub(r"^\s*CARGO\s+\d+\s*:\s*", "", rotulo, flags=re.I)))
    if not r:
        return None
    pares = [n if isinstance(n, tuple) else (n, "") for n in nomes]
    sem = lambda x: re.sub(r"[\s-]", "", x)
    r_ = sem(r)
    for n, e in sorted(pares, key=lambda x: -len(x[1])):      # com especialidade primeiro
        tn, te = sem(N.texto(n)), sem(N.texto(e))
        if tn and (tn in r_ or r_ in tn) and (not te or te in r_):
            return _chave(n, e)
    for n, e in pares:                                        # especialidade com redação diferente no quadro
        tn = sem(N.texto(n))
        if tn and tn in r_ and sum(1 for x, _ in pares if sem(N.texto(x)) == tn) == 1:
            return _chave(n, e)
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
    # "no valor de R$ 200,00 (duzentos reais) para a carreira de A e de R$ 150,00 (…) para a carreira de B"
    for p in paginas:
        tx = " ".join(p.texto.split())
        achou = {}
        for m in re.finditer(r"(R\$\s*[\d.]+,\d{2})\s*(?:\([^)]{0,80}\))?\s*para\s+(?:a\s+carreira|o\s+cargo|os\s+cargos|as\s+carreiras)\s+de\s+"
                             r"(.{3,120}?)(?=\s+e\s+de\s+R\$|\s*[,;.](?:\s|$)|\s*$)", tx, re.I):
            k = _casar_nome(m.group(2), nomes)
            if k:
                achou[k] = Evidencia(N.dinheiro(m.group(1)), "CONFIRMADO", doc, p.numero, " ".join(m.group(0).split()[:30]), url)
        if achou:
            return achou
    ts = taxa(paginas, doc, url)
    if ts and len({t.valor for t in ts}) == 1:
        out["*"] = ts[0]
    return out


_FASES = [
    (r"prova[s]?\s+objetiva", "Prova Objetiva"),
    (r"prova[s]?\s+(?:discursiva|dissertativa)|reda[çc][ãa]o", "Prova Discursiva"),
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
    por_fase = _etapas_numeradas(paginas, doc, url, nomes_cargos)
    if por_fase:
        return None, por_fase
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


def _etapas_numeradas(paginas: list[Pagina], doc: str, url: str, nomes_cargos: list[str]) -> dict:
    """{texto(cargo): ev} a partir de 'para o cargo de X será constituído de N fases' + itens 'Nª Fase - …'."""
    t = "\n".join(p.texto for p in paginas[:6])
    secoes = list(re.finditer(r"para\s+o\s+cargo\s+de\s+(.{3,120}?)\s+ser[áa]\s+constitu[íi]d[oa]\s+de\s+\d+\s*(?:\([^)]*\))?\s*(?:fases|etapas)", t, re.I | re.S))
    out = {}
    for i, sec in enumerate(secoes):
        fim = secoes[i + 1].start() if i + 1 < len(secoes) else sec.end() + 6000
        jan = t[sec.end():fim]
        fases = []
        for m in re.finditer(r"(?m)^\s*(?:\d+(?:\.\d+)*\.?\s+)?\d+ª\s+(?:Fase|Etapa)\s*[-–:]\s*([^\n]+)", jan, re.I):
            item = re.split(r",|\s+de\s+car[áa]ter", m.group(1))[0]
            achados = sorted((mm.start(), nome) for pad, nome in _FASES for mm in [re.search(pad, item, re.I)] if mm)
            fases += [n for _, n in achados]
        k = _casar_nome(" ".join(sec.group(1).split()), [(n, "") for n in nomes_cargos])
        if fases and k:
            pg = _pagina_de(paginas, " ".join(sec.group(0).split()[:6]))
            out[k] = Evidencia(", ".join(dict.fromkeys(fases)), "CONFIRMADO", doc, pg, trecho(t, sec.start(), sec.end()), url)
    return out


def cidades(paginas: list[Pagina], doc: str, url: str) -> Evidencia | None:
    """Cidades de aplicação da prova objetiva."""
    for p in paginas:
        m = re.search(r"(?:provas?|objetivas?)[^.]{0,400}?(?:ser[ãa]o|ser[áa])\s+(?:realizad|aplicad)[oa]s?\s+n[oa]s?\s+"
                      r"(?:munic[íi]pios?|cidades?|localidades?)\s+de\s+(.{3,300})", p.texto, re.I | re.S)
        if not m:
            continue
        lista = " ".join(m.group(1).split())
        lista = re.split(r"\.(?:\s|$)|;", lista)[0]
        lista = re.split(r",\s*(?:no|na|nos|nas|do|da|com|sendo|em|conforme)\b|\s+no\s+Estado|\s+com\s|\s*\(", lista)[0]
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
    # trecho de frase em vez de nome ("cargos de Agente … da Polícia Civil do Estado de X"): fica com o último órgão citado
    if re.search(r"CARGO|ESCRIV|CUMPRIR|JORNADA|SERVIDORES|AUXILIARES|VAGAS", N.texto(n)):
        ult = list(re.finditer(rf"\bD[AOE]S?\s+(?={_ORGAO_INICIO})", n, re.I))
        cand = n[ult[-1].end():] if ult else ""
        if not cand or re.search(r"CARGO|ESCRIV|CUMPRIR|JORNADA|SERVIDORES|AUXILIARES|VAGAS", N.texto(cand)):
            return ""
        n = cand
    n = re.sub(r"^MUNIC[ÍI]PIO DE ", "PREFEITURA MUNICIPAL DE ", n, flags=re.I)
    if re.match(r"(SECRETARIA|CONTROLADORIA|PROCURADORIA)[- ]\S*\s*(MUNICIPAL|GERAL DO MUN)", N.texto(n)) and not re.search(r"\bDE\s+[A-Z]{3,}\s*$", N.texto(n).replace("MUNICIPAL DE ", "")):
        cab = "\n".join(p.texto for p in paginas[:2])
        m = re.search(r"(?:PREFEITURA(?: MUNICIPAL)?|MUNIC[ÍI]PIO)\s+D[EO]\s+([A-ZÀ-Ú][A-ZÀ-Ú ]{2,40}?)(?:\s*[/–-]\s*[A-Z]{2}\b|\n|,|\.)", cab, re.I)
        if m:
            n = f"PREFEITURA MUNICIPAL DE {re.sub(r'^(?:MUNIC[ÍI]PIO|PREFEITURA)\s+DE\s+', '', m.group(1).strip(), flags=re.I).upper()} – {n}"
    return n.upper()


def recortar_edital(paginas: list[Pagina]) -> list[Pagina]:
    """Em edição de Diário Oficial, descarta os atos anteriores ao edital de abertura (aposentadorias, resultados…).
    Início = linha 'EDITAL … ABERTURA' ou 'EDITAL Nº' seguida, em até 1.500 caracteres, de 'torna público' / 'faz saber' /
    'abertas as inscrições'."""
    for i, p in enumerate(paginas[:6]):
        for m in re.finditer(r"(?m)^\s*EDITAL\b[^\n]*(?:ABERTURA|N[º°o.]\s*\d)", p.texto):
            depois = p.texto[m.start():m.start() + 1500] + (paginas[i + 1].texto[:800] if i + 1 < len(paginas) else "")
            if re.search(r"torna(?:m)?\s+p[úu]blic|faz(?:em)?\s+saber|abertas?\s+as\s+inscri|realiza[çc][ãa]o\s+de\s+concurso|RESOLVE(?:M)?\s*:\s*I\.?\s*Abrir", depois, re.I):
                if i == 0 and m.start() < 400:
                    return _ate_proximo_edital(paginas, 0, 0)          # o PDF já começa no edital
                primeira = Pagina(p.numero, p.texto[m.start():], p.tabelas, p.ocr)
                return _ate_proximo_edital([primeira] + paginas[i + 1:], 0, 0)
    return paginas


def _ate_proximo_edital(paginas: list[Pagina], i0: int, pos0: int) -> list[Pagina]:
    """Corta no início do próximo edital de abertura da mesma edição do Diário Oficial (ex.: PMPE e CBMPE publicados
    juntos em 29/09/2026). Exige outro cabeçalho 'EDITAL DE ABERTURA' seguido de 'torna público' ou equivalente."""
    for i, p in enumerate(paginas):
        ini = 400 if i == 0 else 0
        for m in re.finditer(r"(?m)^\s*EDITAL\s+DE\s+ABERTURA\b", p.texto[ini:]):
            k = ini + m.start()
            depois = p.texto[k:k + 1500] + (paginas[i + 1].texto[:800] if i + 1 < len(paginas) else "")
            if not re.search(r"torna(?:m)?\s+p[úu]blic|faz(?:em)?\s+saber|abertas?\s+as\s+inscri|RESOLVE(?:M)?\s*:\s*I\.?\s*Abrir", depois, re.I):
                continue
            # quadros da página do corte ficam só se o corte estiver na metade de baixo
            tabs = p.tabelas if k > len(p.texto) / 2 else []
            ultima = Pagina(p.numero, p.texto[:k], tabs, p.ocr)
            return paginas[:i] + ([ultima] if k > 0 else [])
    return paginas


# ---------------------------------------------------------------- validações e campos de qualidade (auditoria 08/10/2026)
# profissões de nível superior (texto já normalizado: maiúsculas, sem acento)
_SUPERIOR_PROF = re.compile(
    r"\b(?:MEDIC[OA]|ENGENHEIR[OA]|ADVOGAD[OA]|PROCURADOR|CONTADOR|PSICOLOG[OA]|ENFERMEIR[OA]|FARMACEUTIC[OA]|"
    r"NUTRICIONISTA|ARQUITET[OA]|FISIOTERAPEUTA|ODONTOLOG[OA]|CIRURGIA?O[- ]DENTISTA|DENTISTA|ASSISTENTE SOCIAL|"
    r"DELEGAD[OA]|PERIT[OA]|AUDITOR|ANALISTA|ECONOMISTA|BIBLIOTECARI[OA]|VETERINARI[OA]|FONOAUDIOLOG[OA]|BIOLOG[OA]|"
    r"GEOLOG[OA]|ESTATISTIC[OA]|PROFESSOR|PEDAGOG[OA]|DEFENSOR|JUIZ|PROMOTOR|CONSULTOR LEGISLATIVO|CONTROLADOR INTERNO|"
    r"TECNOLOG[OA]|ESPECIALISTA EM POLITICAS|DIRETOR DE ESCOLA|\bPEB\b)\b")


def nivel_do_cargo(nome: str, especialidade: str = "") -> tuple[str | None, str]:
    """Nível de escolaridade (Fundamental, Técnico, Médio ou Superior) pelo nome do cargo, quando o edital não o dá
    no quadro. Devolve (nível, status): 'Nível X' no nome é CONFIRMADO; profissão regulamentada é INDÍCIO."""
    t = N.texto(f"{nome} {especialidade}")
    m = re.search(r"N[IÍ]VEL\s+(FUNDAMENTAL|T[EÉ]CNICO|M[EÉ]DIO|SUPERIOR)", t)
    if m:
        return N.nivel(m.group(1)), "CONFIRMADO"
    if re.match(r"(?:T[EÉ]CNICO|TECNICO)\s+(?:EM|DE|DO|DA)\b", t):
        return "Técnico", "INDÍCIO"
    if _SUPERIOR_PROF.search(t):
        return "Superior", "INDÍCIO"
    return None, ""


def objeto_do_edital(paginas: list[Pagina], doc: str, url: str) -> Evidencia | None:
    """Frase do edital que diz o objeto, a partir de 'Concurso Público'/'Processo Seletivo' logo depois de 'torna
    público' / 'faz saber' / 'RESOLVEM' / 'realizará' (ex.: 'Concurso Público para formação de cadastro de reserva
    destinado ao provimento de cargos vagos das carreiras de …')."""
    t = " ".join(_texto_todo(paginas, 3).split())
    for gat in re.finditer(r"torna(?:m)?\s+p[úu]blic[ao]s?|faz(?:em)?\s+saber|RESOLVE(?:M)?\s*:|realizar[áa]", t, re.I):
        jan = t[gat.end():gat.end() + 260]
        m = re.search(r"(Concurso\s+P[úu]blico|Processo\s+Seletivo(?:\s+P[úu]blico)?(?:\s+Simplificado)?)", jan, re.I)
        if not m:
            continue
        ini = gat.end() + m.start()
        resto = t[ini:ini + 420]
        resto = re.split(r",\s*(?:o\s+qual|que\s+se\s+reger|regid[oa]|sob\s+(?:a\s+)?(?:organiza|responsabilidade)|mediante|"
                         r"nos\s+termos|com\s+ingresso|observad)|\.\s|;", resto, maxsplit=1)[0]
        resto = re.sub(r"\s+N[º°o.]*\s*\d+/\d{4}", "", resto, count=1).strip(" ,")
        if len(resto) < 25:
            # "abertas inscrições de Concurso Público, regido pelas Instruções…, para provimento dos empregos …"
            mm = re.search(r"para\s+(?:o\s+|a\s+)?(?:provimento|preenchimento|forma[çc][ãa]o)[^.;]{10,250}", t[ini:ini + 500], re.I)
            if not mm:
                continue
            resto = f"{resto} {re.split(r',\s*(?:sob|regid|o\s+qual)', mm.group(0))[0]}".strip(" ,")
        # "PROCESSO SELETIVO PÚBLICO, destinado …" → "Processo Seletivo Público, destinado …"
        resto = re.sub(r"^[A-ZÀ-Ú ]{8,}(?=[,\s])", lambda x: _titulo(x.group(0)), resto)
        frase = resto[0].upper() + resto[1:]
        return Evidencia(frase, "CONFIRMADO", doc, _pagina_de(paginas, t[ini:ini + 40]), " ".join(frase.split()[:30]), url)
    return None


def tipo_do_edital(paginas: list[Pagina]) -> str | None:
    """'processo_seletivo' quando o próprio edital se declara processo seletivo; 'concurso' quando concurso público."""
    t = N.texto(_texto_todo(paginas, 2)[:4000])
    ps, cp = t.find("PROCESSO SELETIVO"), t.find("CONCURSO PUBLICO")
    if ps >= 0 and (cp < 0 or ps < cp):
        return "processo_seletivo"
    if cp >= 0:
        return "concurso"
    return None


_CLIENTE_INVALIDO = re.compile(r"\bLTDA\b|\bEIRELI\b|\bS/?A\s+-?\s*ME\b|\b\d+\s*[ªº°]\s*CLASSE\b|^EMPRESA\b|^MG E\b|^O\s", re.I)


def cliente_valido(nome: str) -> bool:
    return bool(nome) and not _CLIENTE_INVALIDO.search(nome) and len(nome) >= 6


def limpar_cargo(nome: str) -> str:
    nome = re.sub(r"^(?:O|A|Os|As)\s+(?=[A-ZÀ-Ú])", "", nome.strip())
    if nome.isupper():
        nome = _titulo(nome)
    return nome


def cargo_valido(nome: str) -> bool:
    """Descarta códigos soltos ('B02') e rótulos que não são cargo."""
    return bool(nome) and not re.fullmatch(r"[A-Z]{0,3}\d{1,4}[A-Z]?", nome.strip()) and len(nome.strip()) >= 4


def limpar_cidades(s: str) -> str:
    s = re.split(r"\s+[–-]\s+|\s+no\s+per[íi]odo\b|,\s*podendo\b|,\s*a\s+crit[ée]rio\b|\s+conforme\b", s)[0]
    return s.strip(" ,;")


def preencher_certame(certame, paginas: list[Pagina], doc: str, url: str, uf_reserva: str = "") -> None:
    """Preenche órgão, UF, cargos e campos do certame a partir do edital de abertura já lido."""
    from modelos import Cargo
    completas = paginas
    paginas = recortar_edital(paginas)
    orgao, ev_org = orgao_do_edital(paginas, doc, url, completas)
    if orgao:
        orgao = limpar_orgao(orgao, paginas) or None
    if orgao:
        certame.orgao = orgao
    cid = cidades(paginas, doc, url)
    if cid:
        cid.valor = limpar_cidades(cid.valor) or None
        cid = cid if cid.valor else None
    obj = objeto_do_edital(paginas, doc, url)
    if obj:
        certame.campos_certame["OBJETO"] = obj
    tp = tipo_do_edital(paginas)
    if tp and certame.tipo in ("", "concurso", None):
        certame.tipo = tp
    uf_cid = re.search(r"/([A-Z]{2})\b", cid.trecho).group(1) if cid and re.search(r"/([A-Z]{2})\b", cid.trecho) else ""
    certame.uf = N.uf_no_texto(certame.orgao) or uf_cid or uf_reserva or ""
    cargos = cargos_blocos(paginas, doc, url)
    nomes = [(c["nome"], c.get("especialidade", "")) for c in cargos]
    vagas = vagas_por_cargo(paginas, doc, url, nomes)
    taxas = taxas_por_cargo(paginas, doc, url, nomes)
    for c in cargos:
        if not cargo_valido(c["nome"]):
            continue
        cg = Cargo(limpar_cargo(c["nome"]), c.get("especialidade", ""))
        for col in ("SALARIO", "NIVEL", "TAXA"):
            if c.get(col) and c[col].valor is not None:
                cg.campos[col] = c[col]
        k = _chave(c["nome"], c.get("especialidade", ""))
        k0 = _chave(c["nome"])
        cg.campos.update(vagas.get(k) or vagas.get(k0) or (vagas.get("*") if len(cargos) == 1 else {}) or {})
        for col in ("VAGAS", "VAGAS_CR"):          # quadro do próprio cargo (_cargos_quadro)
            if c.get(col):
                cg.campos[col] = c[col]
        if k in taxas or k0 in taxas:
            cg.campos["TAXA"] = taxas.get(k) or taxas[k0]
        niv = cg.campos.get("NIVEL")
        if niv is not None and niv.valor not in ("Fundamental", "Técnico", "Médio", "Superior"):
            niv.valor = N.nivel(niv.valor)
            if not niv.valor:
                cg.campos.pop("NIVEL")
        if "NIVEL" not in cg.campos and obj and len(set(re.findall(r"n[íi]vel\s+(superior|m[ée]dio|t[ée]cnico|fundamental)", obj.valor, re.I))) == 1:
            nv = N.nivel(re.search(r"n[íi]vel\s+(superior|m[ée]dio|t[ée]cnico|fundamental)", obj.valor, re.I).group(1))
            cg.campos["NIVEL"] = Evidencia(nv, "CONFIRMADO", doc, obj.pagina, obj.trecho, url)
        if "NIVEL" not in cg.campos:
            v, st = nivel_do_cargo(cg.nome, cg.especialidade)
            if v:
                cg.campos["NIVEL"] = Evidencia(v, st, doc, None, f"nível pelo nome do cargo: {cg.nome}"[:200], url)
        certame.cargos.append(cg)
    if "*" in taxas:
        certame.campos_certame["TAXA"] = taxas["*"]
    ev, ev_cargo = etapas(paginas, doc, url, [n for n, _ in nomes])
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
