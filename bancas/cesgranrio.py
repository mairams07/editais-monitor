"""Adaptador Cesgranrio.

Etapa 0 (06/10/2026): site devolve 403 (inclusive com navegador) — BLOQUEADO. O edital vem de site de notícias
(autorizado em 06/10/2026), conferido pelo conteúdo do PDF.
"""
from __future__ import annotations

from bancas.base import Adaptador
from bancas.noticias import AdaptadorNoticias


class Cesgranrio(AdaptadorNoticias, Adaptador):
    chave = "cesgranrio"
    inicio = "https://www.cesgranrio.org.br/"
    banca_regex = r"CESGRANRIO"
    termos = ["Cesgranrio edital publicado", "Fundação Cesgranrio edital", "Cesgranrio banca edital"]
