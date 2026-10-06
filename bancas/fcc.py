"""Adaptador FCC.

Etapa 0 (06/10/2026): robots.txt do site proíbe /concursos/ e *.pdf — páginas de certame e editais não são lidos.
As páginas de lista (concursoNovo/InscricaoAberta/Andamento/OutraSituacao.html) são permitidas e dão órgão e código
do certame (código termina no ano: dpepb126 = DPE-PB, 1º de 2026). O edital vem de site de notícias
(autorizado em 06/10/2026), conferido pelo conteúdo do PDF.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from bancas.base import Adaptador
from bancas.noticias import AdaptadorNoticias

LISTAS = ["concursoNovo", "concursoInscricaoAberta", "concursoAndamento", "concursoOutraSituacao"]


class Fcc(AdaptadorNoticias, Adaptador):
    chave = "fcc"
    inicio = "https://www.concursosfcc.com.br/concursoAndamento.html"
    banca_regex = r"FUNDACAO CARLOS CHAGAS|\bFCC\b"
    termos = ["FCC edital publicado", "Fundação Carlos Chagas edital"]

    def termos_busca(self, ano: int) -> list[str]:
        yy = str(ano)[-2:]
        orgaos = {}
        for lista in LISTAS:
            html = self.acesso.html(f"https://www.concursosfcc.com.br/{lista}.html", self.chave)
            s = BeautifulSoup(html, "html.parser")
            for a in s.find_all("a", href=True):
                m = re.search(r"concursos/([a-z]+)\d(\d{2})/", a["href"])
                if m and m.group(2) == yy:
                    orgaos.setdefault(m.group(1), a.get_text(" ", strip=True))
        self.lista_oficial = orgaos      # para o relatório: certames 2026 que a FCC lista
        return self.termos + [f"{nome} edital" for nome in orgaos.values() if nome]
