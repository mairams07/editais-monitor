"""Adaptador Instituto AOCP.

Etapa 0 (06/10/2026): Cloudflare libera a 1ª página e bloqueia as seguintes; os PDFs (arquivos-site.institutoaocp.org.br) abrem por HTTP simples.
Por autorização de 06/10/2026, a fonte é o PDF do edital localizado em site especializado em concursos
(ver bancas/noticias.py), conferido pelo conteúdo do PDF; status CONFIRMADO.
"""
from __future__ import annotations

from bancas.base import Adaptador
from bancas.noticias import AdaptadorNoticias


class Aocp(AdaptadorNoticias, Adaptador):
    chave = "aocp"
    inicio = "https://www.institutoaocp.org.br/"
    banca_regex = r"INSTITUTO AOCP|\\bAOCP\\b"
    termos = ['Instituto AOCP edital publicado', 'AOCP edital', 'AOCP banca edital']
