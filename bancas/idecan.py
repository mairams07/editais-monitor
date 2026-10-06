"""Adaptador IDECAN.

Etapa 0 (06/10/2026): a home lista os certames, mas concurso.idecan.org.br exige captcha (Cloudflare Turnstile).
Por autorização de 06/10/2026, a fonte é o PDF do edital localizado em site especializado em concursos
(ver bancas/noticias.py), conferido pelo conteúdo do PDF; status CONFIRMADO.
"""
from __future__ import annotations

from bancas.base import Adaptador
from bancas.noticias import AdaptadorNoticias


class Idecan(AdaptadorNoticias, Adaptador):
    chave = "idecan"
    inicio = "https://idecan.org.br/"
    banca_regex = r"IDECAN"
    termos = ['Idecan edital publicado', 'Idecan edital', 'Idecan banca edital']
