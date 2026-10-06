"""Adaptador Vunesp.

Etapa 0 (06/10/2026): o site recusa HTTP simples (Akamai); pelo navegador abre algumas páginas e depois devolve 403, inclusive nos PDFs.
Por autorização de 06/10/2026, a fonte é o PDF do edital localizado em site especializado em concursos
(ver bancas/noticias.py), conferido pelo conteúdo do PDF; status CONFIRMADO.
"""
from __future__ import annotations

from bancas.base import Adaptador
from bancas.noticias import AdaptadorNoticias


class Vunesp(AdaptadorNoticias, Adaptador):
    chave = "vunesp"
    inicio = "https://www.vunesp.com.br/"
    banca_regex = r"VUNESP"
    termos = ['Vunesp edital publicado', 'Fundação Vunesp edital', 'Vunesp banca edital']
