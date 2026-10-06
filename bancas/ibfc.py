"""Adaptador IBFC.

Etapa 0 (06/10/2026): site abre por HTTP simples; robots.txt bloqueia só /admin, /painel e /uploads.
  - listas:  /index/abertos/, /index/1/ (em andamento), /index/3/ (finalizados) → /informacoes/{id}/
  - página do certame: links com título e data ("Edital de Abertura nº 01/2026 - Retificado 12/06/2026")
  - arquivos em servidor-arquivos.ibfc.org.br/arquivos-publicos/ (permitido)
Data de publicação = data do link "Edital de Abertura" (a versão retificada, se houver, é a lida).
"""
from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup

import normalizacao as N
from bancas.base import Adaptador
from extracao import campos, pdf
from modelos import Certame, Documento

BASE = "https://concursos.ibfc.org.br"
LISTAS = ["/index/abertos/", "/index/1/", "/index/3/"]


def _data(txt: str) -> date | None:
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s*$", txt.strip())
    return datetime.strptime("/".join(m.groups()), "%d/%m/%Y").date() if m else None


class Ibfc(Adaptador):
    chave = "ibfc"
    inicio = BASE + LISTAS[0]

    def listar_certames(self, ano: int) -> list[Certame]:
        ids = {}
        for l in LISTAS:
            s = BeautifulSoup(self.acesso.html(BASE + l, self.chave), "html.parser")
            for a in s.find_all("a", href=True):
                m = re.search(r"/informacoes/(\d+)/", a["href"])
                txt = " ".join(a.get_text(" ", strip=True).split())
                if m and (f"/{ano}" in txt or f"{ano - 1}" in txt):
                    ids.setdefault(m.group(1), txt)
        saida = []
        for i, titulo in ids.items():
            url = f"{BASE}/informacoes/{i}/"
            s = BeautifulSoup(self.acesso.html(url, self.chave), "html.parser")
            links = [(" ".join(a.get_text(" ", strip=True).split()), a["href"]) for a in s.find_all("a", href=True)
                     if a["href"].lower().endswith(".pdf")]
            ab = [(t, h) for t, h in links if re.search(r"edital de abertura|edital n[ºo°.]*\s*\d+/\d{4}$", t, re.I)
                  and not re.search(r"retifica[çc][ãa]o n", t, re.I)]
            if not ab:
                continue
            datas = [d for d in (_data(t) for t, _ in ab) if d]
            if not datas or min(datas).year != ano:
                continue
            c = Certame("ibfc", i, url, titulo=titulo, publicado_em=min(datas), tipo=self._tipo(titulo))
            # edital mais recente (retificado/consolidado) é o lido
            t, h = sorted(ab, key=lambda x: _data(x[0]) or date.min)[-1]
            c.extra["docs"] = [Documento(t, h, "edital", _data(t))]
            saida.append(c)
        return saida

    @staticmethod
    def _tipo(titulo: str) -> str:
        t = N.texto(titulo)
        if "APRENDIZ" in t or "SELETIVO" in t or "ESTAGI" in t:
            return "processo_seletivo"
        if "RESIDENCIA" in t:
            return "residencia"
        return "concurso"

    def listar_documentos(self, certame: Certame) -> list[Documento]:
        return certame.extra.get("docs", [])

    def extrair(self, certame: Certame) -> None:
        ed = certame.documentos[0]
        pags = pdf.ler(ed.caminho_local)
        campos.preencher_certame(certame, pags, ed.titulo, ed.url)
