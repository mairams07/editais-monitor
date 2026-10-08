"""Leitura do edital por IA (Claude), com conferência de cada valor no próprio PDF.

Por que existe: as regras fixas de extracao/campos.py não acompanham a variedade de formatos de edital (auditoria de
08/10/2026). Aqui o modelo lê o texto do edital, página a página, e devolve cada campo com a página e o trecho literal
de onde tirou o valor. Nada entra sem passar pela conferência local:
  - o trecho precisa existir, palavra por palavra, na página indicada (tolerância só para espaços e hifenização);
  - o valor precisa aparecer no trecho (números conferidos pelo valor, não pela formatação);
  - nível de escolaridade só Fundamental, Técnico, Médio ou Superior.
Valor que falha na conferência é descartado e registrado no LOG como "NÃO LOCALIZADO (trecho não confere)".

Requer a variável ANTHROPIC_API_KEY (ou `ant auth login`). Sem credencial, o monitor segue com a extração por regras.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

import normalizacao as N
from extracao.pdf import Pagina
from modelos import Cargo, Evidencia

MODELO = "claude-opus-5-5"
NIVEIS = ["Fundamental", "Técnico", "Médio", "Superior"]

_CAMPO = {
    "type": "object",
    "properties": {
        "valor": {"type": ["string", "null"]},
        "pagina": {"type": ["integer", "null"]},
        "trecho": {"type": ["string", "null"]},
    },
    "required": ["valor", "pagina", "trecho"],
    "additionalProperties": False,
}

ESQUEMA = {
    "type": "object",
    "properties": {
        "eh_edital_de_abertura": {"type": "boolean"},
        "orgao": _CAMPO,
        "objeto": _CAMPO,
        "tipo": {"type": "string", "enum": ["concurso", "processo_seletivo", "residencia", "vestibular_exame"]},
        "uf": _CAMPO,
        "cidades": _CAMPO,
        "etapas": _CAMPO,
        "taxa_unica": _CAMPO,
        "cargos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cargo": {"type": "string"},
                    "especialidade": {"type": ["string", "null"]},
                    "nivel": _CAMPO,
                    "salario": _CAMPO,
                    "vagas": _CAMPO,
                    "vagas_cr": _CAMPO,
                    "taxa": _CAMPO,
                    "etapas": _CAMPO,
                },
                "required": ["cargo", "especialidade", "nivel", "salario", "vagas", "vagas_cr", "taxa", "etapas"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["eh_edital_de_abertura", "orgao", "objeto", "tipo", "uf", "cidades", "etapas", "taxa_unica", "cargos"],
    "additionalProperties": False,
}

INSTRUCOES = """Você extrai dados de um edital de abertura de concurso público ou processo seletivo brasileiro para uma
planilha de inteligência competitiva. O texto vem dividido em páginas marcadas com "=== PÁGINA n ===".

Regras:
- Use somente o que está escrito no edital. Não complete com conhecimento próprio. Campo sem suporte no texto:
  valor, pagina e trecho = null.
- Para cada valor, informe a página e um trecho LITERAL de até 30 palavras, copiado exatamente da página, que contenha
  o valor. O trecho será conferido automaticamente; trecho reescrito ou resumido faz o valor ser descartado.
- orgao: o órgão ou entidade para quem o concurso é feito (o cliente), com o nome como aparece no edital. Nunca a
  banca organizadora (Cebraspe, FCC, Fundação Carlos Chagas, Cesgranrio, Vunesp, Instituto AOCP, IBFC, IDECAN, FGV).
- objeto: a frase do edital que descreve o concurso (ex.: "Concurso Público para provimento de cargos de …").
- uf: sigla de duas letras do estado do órgão, se o edital indicar; cidades: cidades de aplicação das provas.
- Uma entrada em cargos por cargo/especialidade (ou área/ênfase) com vagas próprias.
- nivel: exatamente "Fundamental", "Técnico", "Médio" ou "Superior", conforme a escolaridade exigida no edital.
- salario: vencimento/subsídio/remuneração inicial do cargo, como número com ponto decimal (ex.: "7327.04").
  Se o edital só der faixa ("até R$ …"), deixe null.
- vagas: número de vagas imediatas; "-" quando o edital diz que é só cadastro de reserva. vagas_cr: número do
  cadastro de reserva, se houver.
- taxa: valor da inscrição daquele cargo (número com ponto decimal); taxa_unica quando a taxa é igual para todos.
- etapas: fases do certame em lista separada por vírgula, com nomes curtos (ex.: "Prova Objetiva, Prova Discursiva,
  Avaliação de Títulos").
- eh_edital_de_abertura: false se o documento for retificação, resultado, convocação, extrato ou outro ato."""


# marcas no texto normalizado (maiúsculas, sem acento)
_MARCAS = [(re.compile(r"R\$\s*[\d.]+,\d{2}"), 3), (re.compile(r"\bVAGAS?\b"), 2), (re.compile(r"CADASTRO DE RESERVA"), 2),
           (re.compile(r"TAXA DE INSCRICAO|VALOR DA INSCRICAO|VALOR DA TAXA"), 5),
           (re.compile(r"\bCARGOS?\b|\bEMPREGOS?\b|\bENFASES?\b"), 1),
           (re.compile(r"REMUNERACAO|VENCIMENTO|SUBSIDIO|SALARIO"), 3), (re.compile(r"ESCOLARIDADE|REQUISITO"), 2),
           (re.compile(r"SERAO REALIZADAS? NAS? CIDADES?|NA CIDADE DE|NOS MUNICIPIOS DE|CIDADES? DE (?:REALIZACAO|APLICACAO)"), 6),
           (re.compile(r"QUADRO DE VAGAS|DISTRIBUICAO DAS VAGAS|AMPLA CONCORRENCIA"), 4)]


_CIDADES = re.compile(r"SERAO REALIZADAS? NAS? CIDADES?|(?:PROVAS?|OBJETIVAS?)[^.]{0,200}?REALIZAD[AO]S? NAS? (?:CIDADES?|MUNICIPIOS?) DE")


def selecionar_paginas(paginas: list[Pagina], inicio: int = 4, maximo: int = 12,
                       max_caracteres: int = 60000) -> list[Pagina]:
    """Páginas que interessam à planilha, sem ler o edital inteiro (pedido de 08/10/2026: cargos, vagas, taxa,
    cidade e estado estão no começo). Sempre as `inicio` primeiras; depois as de maior pontuação por marcas de
    quadro de vagas/remuneração/taxa/cidades (anexos de cargos costumam estar no fim), até `maximo` páginas."""
    def pontos(p):
        t = N.texto(p.texto)
        pt = sum(peso * (1 if rx.search(t) else 0) for rx, peso in _MARCAS)       # presença, não repetição
        pt += 2 * min(len(_MARCAS[0][0].findall(t)), 5)                          # valores em R$
        # quadro de vagas/remuneração: tabela com 2+ linhas que têm números
        for tab in p.tabelas:
            linhas_num = sum(1 for r in tab if sum(1 for c in r if c and re.search(r"\d", str(c))) >= 2)
            if linhas_num >= 2:
                pt += 12
        if _CIDADES.search(t):
            pt += 15
        return pt
    # ordem de prioridade: as primeiras páginas, depois as de maior pontuação; para ao atingir o teto de páginas
    # ou de tamanho (página de Diário Oficial chega a 5 mil palavras)
    fila = paginas[:inicio] + sorted(paginas[inicio:], key=pontos, reverse=True)
    escolhidas, total = [], 0
    for p in fila:
        tam = len(p.texto) + sum(len(str(c or "")) for t in p.tabelas for r in t for c in r)
        if len(escolhidas) >= maximo or (escolhidas and len(escolhidas) >= 2 and total + tam > max_caracteres):
            continue
        escolhidas.append(p)
        total += tam
    return sorted(escolhidas, key=lambda p: p.numero)


def texto_paginado(paginas: list[Pagina]) -> str:
    partes = []
    for p in paginas:
        tabelas = ""
        for t in p.tabelas:
            linhas = [" | ".join(" ".join(str(c or "").split()) for c in r) for r in t]
            tabelas += "\n[tabela]\n" + "\n".join(linhas)
        partes.append(f"=== PÁGINA {p.numero} ===\n{p.texto}{tabelas}")
    return "\n\n".join(partes)


def chamar_modelo(paginas: list[Pagina], cliente=None) -> dict:
    """Uma chamada ao modelo com saída estruturada. Devolve o JSON bruto (ainda não conferido)."""
    import anthropic
    cliente = cliente or anthropic.Anthropic()
    with cliente.beta.messages.stream(
        model=MODELO,
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": ESQUEMA}},
        system=INSTRUCOES,
        messages=[{"role": "user", "content": texto_paginado(paginas)}],
    ) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        raise RuntimeError("o modelo recusou a leitura deste documento")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("resposta cortada (max_tokens)")
    texto = next(b.text for b in resp.content if b.type == "text")
    return json.loads(texto)


# ------------------------------------------------------------------ conferência local
def _plano(s: str) -> str:
    """Normaliza para comparar trecho × página: sem acento, maiúsculas, sem hifenização de quebra, espaços únicos."""
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s or "")
    return " ".join(N.texto(s).split())


def _numero(s) -> Decimal | None:
    if s is None:
        return None
    t = str(s).strip().replace("R$", "").strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}", t):
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t):     # "R$ 3.000" (milhar sem centavos)
        t = t.replace(".", "")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _valor_no_trecho(valor: str, trecho: str, numerico: bool) -> bool:
    if not numerico:
        return True
    alvo = _numero(valor)
    if alvo is None:
        return False
    for m in re.finditer(r"\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+(?:,\d{2})?", trecho):
        if _numero(m.group(0)) == alvo:
            return True
    return False


def conferir(campo: dict | None, paginas: dict[int, str], doc: str, url: str, numerico: bool = False) -> tuple[Evidencia | None, str]:
    """(evidência, motivo). Evidência só quando o trecho existe na página e contém o valor."""
    if not campo or campo.get("valor") in (None, ""):
        return None, "não informado no edital"
    pag, trecho = campo.get("pagina"), campo.get("trecho") or ""
    if not trecho or pag not in paginas:
        return None, "sem página/trecho"
    if _plano(trecho) not in paginas[pag]:
        # tolera trecho que atravessa a quebra de página
        junto = paginas[pag] + " " + paginas.get(pag + 1, "")
        if _plano(trecho) not in junto:
            return None, "trecho não confere com a página"
    if not _valor_no_trecho(campo["valor"], trecho, numerico):
        return None, "valor não aparece no trecho"
    trecho30 = " ".join(trecho.split()[:30])
    return Evidencia(campo["valor"], "CONFIRMADO", doc, pag, trecho30, url), ""


def aplicar(certame, bruto: dict, paginas: list[Pagina], doc: str, url: str) -> list[dict]:
    """Preenche o certame com o que passou na conferência. Devolve a lista de descartes para o LOG."""
    pags = {p.numero: _plano(p.texto + " " + " ".join(" ".join(str(c or "") for c in r) for t in p.tabelas for r in t))
            for p in paginas}
    descartes = []

    def ev(nome, campo, numerico=False, cargo=""):
        e, motivo = conferir(campo, pags, doc, url, numerico)
        if motivo and motivo != "não informado no edital":
            descartes.append({"cargo": cargo, "campo": nome, "valor": (campo or {}).get("valor"), "motivo": motivo})
        return e

    if not bruto.get("eh_edital_de_abertura", True):
        descartes.append({"cargo": "", "campo": "documento", "valor": "", "motivo": "o modelo indicou que não é edital de abertura"})
    org = ev("CLIENTE", bruto.get("orgao"))
    if org and not N.banca(org.valor):
        certame.orgao = " ".join(org.valor.split()).upper()
    obj = ev("OBJETO", bruto.get("objeto"))
    if obj:
        certame.campos_certame["OBJETO"] = obj
    if bruto.get("tipo"):
        certame.tipo = bruto["tipo"]
    uf = ev("UF", bruto.get("uf"))
    if uf and str(uf.valor).upper() in N.UFS:
        uf.valor = str(uf.valor).upper()
        certame.uf = uf.valor
        certame.campos_certame["UF"] = uf
    for nome, chave in (("CIDADES", "cidades"), ("ETAPAS", "etapas")):
        e = ev(nome, bruto.get(chave))
        if e:
            certame.campos_certame[nome] = e
    tx = ev("TAXA", bruto.get("taxa_unica"), numerico=True)
    if tx:
        tx.valor = _numero(tx.valor)
        certame.campos_certame["TAXA"] = tx
    certame.cargos = []
    for c in bruto.get("cargos") or []:
        nome = " ".join((c.get("cargo") or "").split())
        if not nome:
            continue
        cg = Cargo(nome, " ".join((c.get("especialidade") or "").split()))
        rot = f"{cg.nome} {cg.especialidade}".strip()
        niv = ev("NIVEL", c.get("nivel"), cargo=rot)
        if niv and niv.valor in NIVEIS:
            cg.campos["NIVEL"] = niv
        sal = ev("SALARIO", c.get("salario"), numerico=True, cargo=rot)
        if sal:
            sal.valor = _numero(sal.valor)
            cg.campos["SALARIO"] = sal
        vg = c.get("vagas")
        if vg and str(vg.get("valor")).strip() == "-":
            e = ev("VAGAS", vg, cargo=rot)
            if e:
                cg.campos["VAGAS"] = e
        else:
            e = ev("VAGAS", vg, numerico=True, cargo=rot)
            if e:
                e.valor = int(_numero(e.valor))
                cg.campos["VAGAS"] = e
        cr = ev("VAGAS_CR", c.get("vagas_cr"), numerico=True, cargo=rot)
        if cr:
            cr.valor = int(_numero(cr.valor))
            cg.campos["VAGAS_CR"] = cr
        t = ev("TAXA", c.get("taxa"), numerico=True, cargo=rot)
        if t:
            t.valor = _numero(t.valor)
            cg.campos["TAXA"] = t
        et = ev("ETAPAS", c.get("etapas"), cargo=rot)
        if et:
            cg.campos["ETAPAS"] = et
        certame.cargos.append(cg)
    return descartes


def disponivel() -> bool:
    """Há credencial para a API? Variável ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN ou perfil do `ant auth login`.
    (O construtor do cliente não falha sem chave, então não serve de teste.)"""
    import os
    from pathlib import Path
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return (Path.home() / ".config" / "anthropic").exists()
