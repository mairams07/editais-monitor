"""Texto e tabelas de PDF com número de página. OCR (tesseract) quando a página é imagem."""
from __future__ import annotations

from dataclasses import dataclass, field

import pdfplumber


@dataclass
class Pagina:
    numero: int               # 1-based, como aparece no leitor de PDF
    texto: str
    tabelas: list[list[list[str | None]]] = field(default_factory=list)
    ocr: bool = False


def ler(caminho: str, ocr_se_vazio: bool = True) -> list[Pagina]:
    paginas = []
    with pdfplumber.open(caminho) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            txt = p.extract_text() or ""
            tabs = p.extract_tables() or []
            usou_ocr = False
            if ocr_se_vazio and len(txt.strip()) < 30:
                txt, usou_ocr = _ocr(p), True
            paginas.append(Pagina(i, txt, tabs, usou_ocr))
    return paginas


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
