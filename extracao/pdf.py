"""Texto e tabelas de PDF com número de página. OCR (tesseract) quando a página é imagem."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

import pdfplumber


@dataclass
class Pagina:
    numero: int               # 1-based, como aparece no leitor de PDF
    texto: str
    tabelas: list[list[list[str | None]]] = field(default_factory=list)
    ocr: bool = False


def ler(caminho: str, ocr_se_vazio: bool = True, max_paginas: int | None = None, tabelas: bool = True) -> list[Pagina]:
    paginas = []
    with pdfplumber.open(caminho) as pdf:
        for i, p in enumerate(pdf.pages[:max_paginas] if max_paginas else pdf.pages, start=1):
            txt = _texto_colunas(p)
            tabs = (p.extract_tables() or []) if tabelas else []
            usou_ocr = False
            if ocr_se_vazio and len(txt.strip()) < 30:
                txt, usou_ocr = _ocr(p), True
            paginas.append(Pagina(i, _norm(txt), [[[_norm(c) if c else c for c in r] for r in t] for t in tabs], usou_ocr))
    return paginas


def _norm(s: str) -> str:
    """Acentos decompostos (a + ~) viram caractere único; 'ı́' (i sem ponto + acento) vira 'í'."""
    s = s.replace("\u0131\u0301", "í").replace("\u0131", "i")
    return unicodedata.normalize("NFC", s)


def _texto_colunas(pagina) -> str:
    """Texto na ordem de leitura. Página em duas colunas (Diário Oficial) é lida coluna a coluna."""
    palavras = pagina.extract_words() or []
    if len(palavras) > 80:
        meio = pagina.width / 2
        cruzam = sum(1 for w in palavras if w["x0"] < meio - 4 and w["x1"] > meio + 4)
        esq = sum(1 for w in palavras if w["x1"] <= meio)
        dir_ = sum(1 for w in palavras if w["x0"] >= meio)
        if cruzam < 0.02 * len(palavras) and esq > 0.25 * len(palavras) and dir_ > 0.25 * len(palavras):
            a = pagina.crop((0, 0, meio, pagina.height)).extract_text() or ""
            b = pagina.crop((meio, 0, pagina.width, pagina.height)).extract_text() or ""
            return a + "\n" + b
    return pagina.extract_text() or ""


def _ocr(pagina) -> str:
    try:
        import pytesseract
        img = pagina.to_image(resolution=300).original
        return pytesseract.image_to_string(img, lang="por")
    except Exception as e:  # tesseract ausente ou falha: página fica sem texto e o campo vira NÃO LOCALIZADO
        return f""


def trecho(texto: str, inicio: int, fim: int, max_palavras: int = 30) -> str:
    """Trecho literal em volta do match, limitado a 30 palavras."""
    antes = texto[:inicio].split()[-8:]
    meio = texto[inicio:fim].split()
    depois = texto[fim:].split()
    sobra = max(0, max_palavras - len(antes) - len(meio))
    return " ".join(antes + meio + depois[:sobra])
