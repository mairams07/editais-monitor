"""Normalização de texto, bancas, cabeçalhos e valores."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation


def texto(s) -> str:
    """Sem acento, caixa alta, espaços colapsados."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def vazio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


# ---------------------------------------------------------------- bancas
BANCAS = {
    "cebraspe": "Cebraspe",
    "fcc": "FCC",
    "cesgranrio": "Cesgranrio",
    "vunesp": "Vunesp",
    "idecan": "IDECAN",
    "aocp": "Instituto AOCP",
    "ibfc": "IBFC",
}

_ALIAS_BANCA = {
    "CEBRASPE": "cebraspe", "CESPE": "cebraspe", "CESPE/UNB": "cebraspe", "CEBRASPE/CESPE": "cebraspe",
    "FCC": "fcc", "FUNDACAO CARLOS CHAGAS": "fcc",
    "CESGRANRIO": "cesgranrio", "FUNDACAO CESGRANRIO": "cesgranrio",
    "VUNESP": "vunesp", "FUNDACAO VUNESP": "vunesp",
    "IDECAN": "idecan", "INSTITUTO IDECAN": "idecan",
    "AOCP": "aocp", "INSTITUTO AOCP": "aocp",
    "IBFC": "ibfc", "INSTITUTO IBFC": "ibfc",
    "INSTITUTO BRASILEIRO DE FORMACAO E CAPACITACAO": "ibfc",
}


def banca(s) -> str | None:
    """Chave canônica da banca (ex.: 'aocp') ou None se fora da lista."""
    t = texto(s)
    return _ALIAS_BANCA.get(t)


# ---------------------------------------------------------------- cabeçalhos
COLUNAS = {
    "ANO": "ANO", "COD_INTERNO": "COD_INTERNO", "BANCA VENCEDORA": "BANCA", "TIPO": "TIPO",
    "CLIENTE": "CLIENTE", "OBJETO": "OBJETO", "SEGMENTO": "SEGMENTO",
    "SITUACAO DA DEMANDA": "SITUACAO", "COD PROPOSTA": "COD_PROPOSTA", "SITUACAO PROPOSTA": "SITUACAO_PROPOSTA",
    "NIVEL DE ESCOLARIDADE": "NIVEL", "CARGOS": "CARGO", "ESPECIALIDADE": "ESPECIALIDADE",
    "SALARIO": "SALARIO", "VAGAS": "VAGAS", "VAGAS CR": "VAGAS_CR", "ETAPAS": "ETAPAS",
    "TAXA DE INSCRICAO": "TAXA", "HOMOLOGADAS": "HOMOLOGADAS", "UF": "UF", "CIDADES": "CIDADES",
    "RECEITA ESTIMADA": "RECEITA", "VALOR GLOBAL DA VENCEDORA": "VALOR_GLOBAL", "ESFERA": "ESFERA",
}


def coluna(cabecalho) -> str | None:
    return COLUNAS.get(texto(cabecalho))


# ---------------------------------------------------------------- valores
def dinheiro(s) -> Decimal | None:
    """'R$ 1.561,97' → Decimal('1561.97'). Aceita número já numérico."""
    if s is None:
        return None
    if isinstance(s, (int, float, Decimal)):
        return Decimal(str(s)).quantize(Decimal("0.01"))
    t = str(s).replace("R$", "").replace("\xa0", " ").strip()
    if re.search(r"gratuit|isent", t, re.I):
        return Decimal("0.00")
    m = re.search(r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?", t)
    if not m:
        return None
    num = m.group(0).replace(".", "").replace(",", ".")
    try:
        return Decimal(num).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


_NIVEIS = [("FUNDAMENTAL", "Fundamental"), ("TECNIC", "Técnico"), ("MEDIO", "Médio"), ("SUPERIOR", "Superior")]


def nivel(s) -> str | None:
    t = texto(s)
    for k, v in _NIVEIS:
        if k in t:
            return v
    return None


_FEDERAL = ("UNIAO", "FEDERAL", "MINISTERIO", "AGU", "INSS", "IBGE", "IFPA", "INSTITUTO FEDERAL", "UNIVERSIDADE FEDERAL",
            "TRIBUNAL REGIONAL", "TRF", "TRT", "TRE", "STJ", "STF", "TST", "SENADO", "CAMARA DOS DEPUTADOS", "BANCO DO BRASIL",
            "CAIXA ECONOMICA", "PETROBRAS", "EBSERH", "POLICIA FEDERAL", "PRF")
_MUNICIPAL = ("PREFEITURA", "MUNICIPIO", "MUNICIPAL", "CAMARA MUNICIPAL", "SAAE", "AUTARQUIA MUNICIPAL")
_ESTADUAL = ("ESTADO", "ESTADUAL", "SECRETARIA", "TRIBUNAL DE JUSTICA", "DEFENSORIA", "MINISTERIO PUBLICO DO ESTADO",
             "ASSEMBLEIA", "POLICIA CIVIL", "POLICIA MILITAR", "CORPO DE BOMBEIROS", "DETRAN", "TRIBUNAL DE CONTAS DO ESTADO")


def esfera(orgao) -> str | None:
    """Esfera pelo nome do órgão. Devolve None se não for possível afirmar (vai como INDÍCIO no máximo)."""
    t = texto(orgao)
    if any(k in t for k in _MUNICIPAL):
        return "Municipal"
    if re.search(r"\b(FEDERAL|UNIAO)\b", t):
        return "Federal"
    if any(k in t for k in _ESTADUAL):
        return "Estadual"
    if any(re.search(rf"\b{re.escape(k)}\b", t) for k in _FEDERAL):
        return "Federal"
    return None


# Vocabulário da coluna SEGMENTO na aba 2026 (levantado em 06/10/2026). Ordem importa: primeira regra que casar.
_SEGMENTOS = [
    (r"VESTIBULAR", "Vestibular"),
    (r"CAMARA MUNICIPAL|ASSEMBLEIA LEGISLATIVA|CAMARA LEGISLATIVA|CAMARA DOS DEPUTADOS|SENADO", "Legislativo"),
    (r"TRIBUNAL DE CONTAS", "Tribunal de Contas"),
    (r"CONTROLADORIA", "Controladoria"),
    (r"TRIBUNAL DE JUSTICA|PODER JUDICIARIO DO ESTADO", "Tribunal de Justiça"),
    (r"TRIBUNAL REGIONAL|\bTRT\b|\bTRF\b|\bTRE\b", "Tribunal Regional"),
    (r"MINISTERIO PUBLICO", "Ministério Público"),
    (r"DEFENSORIA", "Defensoria Pública"),
    (r"PROCURADORIA|ADVOCACIA[ -]GERAL", "Procuradoria"),
    (r"CONSELHO FEDERAL", "Conselho Federal"),
    (r"CONSELHO REGIONAL", "Conselho Regional"),
    (r"POLICIA|BOMBEIRO|GUARDA MUNICIPAL|SEGURANCA PUBLICA|PENITENCI|SOCIOEDUCA|DETRAN", "Segurança"),
    (r"AGUA|ESGOTO|SANEAMENTO|\bSAAE", "Saneamento"),
    (r"BANCO|CAIXA ECONOMICA", "Bancário"),
    (r"ENERGIA|ELETRIC", "Energia"),
    (r"TRANSPORTE|METRO|TRENS|PORTO|AEROPORTO|RODOVI", "Transporte"),
    (r"HOSPITAL|SAUDE|EBSERH|FUNDACAO MUNICIPAL DE SAUDE", "Saúde"),
    (r"UNIVERSIDADE|INSTITUTO FEDERAL|EDUCACAO|ESCOLA|COLEGIO|\bIF[A-Z]{1,3}\b", "Educação"),
    (r"PREFEITURA|MUNICIPIO DE", "Prefeitura"),
]


def segmento(orgao) -> str | None:
    """Classificação automática do órgão no vocabulário da planilha (sempre INDÍCIO)."""
    t = texto(orgao)
    for padrao, seg in _SEGMENTOS:
        if re.search(padrao, t):
            return seg
    return None


TIPOS = {"concurso": "Concurso", "processo_seletivo": "Processos Seletivos",
         "residencia": "Processos Seletivos", "vestibular_exame": "Exame"}


UFS = {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
       "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"}

_ESTADOS = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE",
    "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA", "MATO GROSSO DO SUL": "MS",
    "MATO GROSSO": "MT", "MINAS GERAIS": "MG", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO",
}


def uf_no_texto(s) -> str | None:
    """UF citada por extenso no nome do órgão ('… do Estado da Bahia'). 'Pará' só com preposição antes."""
    t = texto(s)
    for nome, uf in _ESTADOS.items():                 # nomes compostos vêm antes dos simples na tabela
        if re.search(rf"\b{nome}\b", t):
            return uf
    if re.search(r"\b(?:DO|DE|EST\.?) PARA\b", t):
        return "PA"
    return None


_SIGLAS_ORGAO = {
    r"\bPC\b": "POLICIA CIVIL", r"\bPM\b": "POLICIA MILITAR", r"\bCBM\b": "CORPO DE BOMBEIROS MILITAR",
    r"\bTJ\b": "TRIBUNAL DE JUSTICA", r"\bMP\b": "MINISTERIO PUBLICO", r"\bDPE\b": "DEFENSORIA PUBLICA DO ESTADO",
    r"\bTCE\b": "TRIBUNAL DE CONTAS DO ESTADO", r"\bTCM\b": "TRIBUNAL DE CONTAS DOS MUNICIPIOS",
    r"\bSEFAZ\b": "SECRETARIA DA FAZENDA", r"\bSSP\b": "SECRETARIA DA SEGURANCA PUBLICA",
    r"\bALE\b": "ASSEMBLEIA LEGISLATIVA", r"\bPREF\.?\b": "PREFEITURA", r"\bPM DE\b": "PREFEITURA MUNICIPAL DE",
}
_STOP = {"DE", "DA", "DO", "DAS", "DOS", "E", "EM", "PARA", "A", "O", "GOV", "EST", "-", "/"}


def orgao_tokens(s) -> set[str]:
    """Tokens significativos do nome do órgão, com siglas expandidas."""
    t = texto(s).replace("-", " ").replace("/", " ")
    for sig, exp in _SIGLAS_ORGAO.items():
        t = re.sub(sig, exp, t)
    return {w for w in re.findall(r"[A-Z0-9]+", t) if w not in _STOP and len(w) > 1}
