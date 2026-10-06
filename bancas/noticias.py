"""Editais via sites especializados em concursos.

Autorização: 06/10/2026 para FCC e Cesgranrio; no mesmo dia estendida a todas as bancas, com status CONFIRMADO.
Os sites das bancas bloqueiam leitura automatizada (FCC por robots.txt; Cesgranrio por 403; Vunesp, AOCP e IDECAN
por bloqueio anti-robô). A fonte passa a ser o PDF do edital anexado em matéria de site especializado. Regras:
  - só PDF cujo conteúdo se identifica como edital de abertura DAQUELA banca e datado do ano pedido;
  - registrado no LOG como "cópia do PDF oficial hospedada em <host>"; a conferência com a publicação original
    não é possível porque o site da banca está bloqueado — isso também vai ao LOG;
  - valores vêm do PDF; o texto da matéria serve só para achar o PDF.
Fonte usada: blog do Gran Cursos (API pública do WordPress, robots.txt permite; PDFs em blog-static, permitido).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from urllib.parse import quote, urlparse

import normalizacao as N
from extracao import pdf

GRAN = "https://blog.grancursosonline.com.br/wp-json/wp/v2/posts"
_MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
          "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
# PDFs anexados que claramente não são o edital de abertura
_NAO_EDITAL = re.compile(r"retifica|resultado|convoca|gabarito|homolog|inscritos|banca|comiss|ploa|cronograma|"
                         r"contrato|autoriza|previst|nomea|aprovad|recurso|local|isen|preliminar|definitiv", re.I)


def buscar_posts(acesso, banca: str, termo: str, depois: str, paginas: int = 4) -> list[dict]:
    posts = []
    for pg in range(1, paginas + 1):
        url = (f"{GRAN}?search={quote(termo)}&after={depois}T00:00:00&per_page=50&page={pg}"
               f"&_fields=id,date,link,title,content")
        try:
            lote = json.loads(acesso.texto(url, banca))
        except Exception:
            break
        if not isinstance(lote, list) or not lote:
            break
        posts += lote
        if len(lote) < 50:
            break
    return posts


# Servidores de arquivos das próprias bancas que abrem por HTTP simples: PDF dali é o documento oficial
HOSTS_OFICIAIS = ("arquivos-site.institutoaocp.org.br", "servidor-arquivos.ibfc.org.br", "cdn.cebraspe.org.br")


def pdfs_candidatos(posts: list[dict], ano: int) -> list[tuple[str, str, str]]:
    """(url do PDF, título da matéria, link da matéria) — uploads do ano com nome de edital, ou PDF em servidor oficial."""
    vistos, out = set(), []
    for p in posts:
        html = p.get("content", {}).get("rendered", "")
        for href in re.findall(r'href="([^"]+\.pdf)"', html, re.I):
            nome = href.rsplit("/", 1)[-1]
            oficial = urlparse(href).netloc in HOSTS_OFICIAIS
            if href in vistos or _NAO_EDITAL.search(nome):
                continue
            if not oficial and (f"/uploads/{ano}/" not in href or "edital" not in nome.lower()):
                continue
            vistos.add(href)
            out.append((href, re.sub(r"<[^>]+>", "", p["title"]["rendered"]), p["link"]))
    return out


def verificar(caminho: str, banca_regex: str, ano: int) -> tuple[bool, date | None, list]:
    """O PDF é edital de abertura da banca, do ano pedido? Devolve (ok, data do edital, páginas lidas)."""
    pags = pdf.ler(caminho, max_paginas=3, tabelas=False)
    ini = "\n".join(p.texto for p in pags[:3])
    t = N.texto(ini)
    if not re.search(banca_regex, t):
        return False, None, pags
    if not re.search(r"ABERTURA|TORNA(?:M)? PUBLIC|REALIZACAO DE (?:CONCURSO|PROCESSO)|FAZ SABER", t):
        return False, None, pags
    if re.search(r"^.{0,400}(RETIFICA|RESULTADO|CONVOCA)", t, re.S):
        return False, None, pags
    m = (re.search(rf"EDITAL[^\n]{{0,120}}?\bDE (\d{{1,2}})(?:O)? DE ({'|'.join(_MESES)}) DE ({ano})", t)
         or re.search(rf"(\d{{1,2}})(?:O)? DE ({'|'.join(_MESES)}) DE ({ano})", t))
    if m:
        return True, date(ano, _MESES[m.group(2)], int(m.group(1))), pags
    m = re.search(rf"\b(\d{{1,2}})/(\d{{1,2}})/({ano})\b", t)
    if m:
        return True, date(ano, int(m.group(2)), int(m.group(1))), pags
    if re.search(rf"EDITAL N\D{{0,4}}\d+/{ano}", t):
        return True, None, pags
    return False, None, pags


def host(url: str) -> str:
    return urlparse(url).netloc


def chave_url(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


class AdaptadorNoticias:
    """Mixin: certames descobertos por PDFs de edital anexados em matérias de 2026."""
    banca_regex: str = ""
    termos: list[str] = []

    def termos_busca(self, ano: int) -> list[str]:
        return list(self.termos)

    def listar_certames(self, ano: int):
        from modelos import Certame, Documento
        from extracao import campos
        posts = []
        for termo in self.termos_busca(ano):
            posts += buscar_posts(self.acesso, self.chave, termo, f"{ano}-01-01")
        certames, vistos = [], set()
        for url, titulo, link in pdfs_candidatos(posts, ano):
            if host(url) in HOSTS_OFICIAIS:
                doc = Documento(f"Edital (PDF no servidor oficial {host(url)}; localizado via matéria: {titulo})", url, "edital")
            else:
                doc = Documento(f"Edital (cópia do PDF oficial hospedada em {host(url)}; matéria: {titulo})", url, "edital",
                                copia_terceiro=True)
            try:
                self.baixar(doc)
            except Exception:
                continue
            if doc.sha256 in vistos:
                continue
            vistos.add(doc.sha256)
            try:
                ok, data, pags = verificar(doc.caminho_local, self.banca_regex, ano)
            except Exception:
                continue
            if not ok:
                continue
            orgao, _ = campos.orgao_do_edital(pags, doc.titulo, url)
            doc.publicado_em = data
            c = Certame(self.chave, chave_url(url), link, titulo=titulo, orgao=orgao or "", publicado_em=data or date(ano, 1, 1),
                        documentos=[doc])
            c.extra["data_confirmada"] = data is not None
            certames.append(c)
        return certames

    def listar_documentos(self, certame):
        return certame.documentos

    def baixar(self, doc):
        if doc.caminho_local:
            return doc
        return self.acesso.baixar(doc, self.chave)

    def extrair(self, certame) -> None:
        from extracao import campos
        ed = certame.documentos[0]
        pags = pdf.ler(ed.caminho_local)
        campos.preencher_certame(certame, pags, ed.titulo, ed.url)
