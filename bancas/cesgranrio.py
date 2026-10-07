"""Adaptador Cesgranrio.

Diagnóstico de 07/10/2026: na nuvem o site devolve 403; na rede da FGV abre (HTTP simples e navegador). Por isso:
  1) site oficial (WordPress), funciona no computador da FGV:
     - lista: /wp-json/wp/v2/concurso (tipo de post "concurso", se exposto) ou, senão, as páginas
              /concursos/page/N com links /concurso/{slug}/
     - certame: página /concurso/{slug}/ → PDFs anexados; o edital de abertura é reconhecido pelo conteúdo do PDF
       (banca Cesgranrio, abertura, data do ano pedido), igual ao fluxo de notícias.
  2) se o site oficial bloquear: sites especializados (bancas/noticias.py), autorizado em 06/10/2026.
"""
from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import urljoin, urlparse

from bancas.base import Adaptador, Bloqueado
from bancas.noticias import AdaptadorNoticias, _NAO_EDITAL, verificar
from extracao import campos
from modelos import Certame, Documento

BASE = "https://www.cesgranrio.org.br"


class Cesgranrio(AdaptadorNoticias, Adaptador):
    chave = "cesgranrio"
    inicio = BASE + "/concursos/"
    banca_regex = r"CESGRANRIO"
    termos = ["Cesgranrio edital publicado", "Fundação Cesgranrio edital", "Cesgranrio banca edital"]

    def _certames_site(self) -> dict[str, str]:
        """{url do certame: título}. Tenta a API do WordPress; cai para as páginas de lista."""
        out: dict[str, str] = {}
        try:
            lote = json.loads(self.acesso.texto(f"{BASE}/wp-json/wp/v2/concurso?per_page=100&_fields=link,title,date", self.chave))
            if isinstance(lote, list):
                for p in lote:
                    out[p["link"]] = re.sub(r"<[^>]+>", "", p.get("title", {}).get("rendered", ""))
        except (Bloqueado, ValueError, KeyError, TypeError):
            pass
        if out:
            return out
        for n in range(1, 11):
            url = f"{BASE}/concursos/" if n == 1 else f"{BASE}/concursos/page/{n}"
            try:
                html = self.acesso.html(url, self.chave)
            except Bloqueado:
                break
            novos = {u: "" for u in re.findall(r'href="(https://www\.cesgranrio\.org\.br/concurso/[^"#?]+/)"', html)}
            if not set(novos) - set(out):
                break
            out.update(novos)
        return out

    def _links_documentos(self, url: str, html: str) -> list[tuple[str, str]]:
        """[(url, rótulo)] dos documentos do certame. Aceita PDF direto, uploads do WordPress e links de download sem
        extensão (outros hosts da Cesgranrio); rótulo vem do texto do link ou do elemento anterior."""
        from bs4 import BeautifulSoup
        sopa = BeautifulSoup(html, "html.parser")
        out, vistos = [], set()
        for a in sopa.find_all(["a", "iframe", "embed", "object"]):
            href = a.get("href") or a.get("src") or a.get("data") or a.get("data-href") or ""
            if not href or href.startswith(("#", "mailto:", "javascript:")):
                continue
            u = urljoin(url, href.strip())
            rot = re.sub(r"\s+", " ", a.get_text(" ", strip=True) or a.get("title", "") or "").strip()
            if not rot:
                ant = a.find_previous(string=lambda t: t and t.strip())
                rot = ant.strip()[:120] if ant else ""
            doc = (re.search(r"\.pdf($|[?#])", u, re.I) or "/wp-content/uploads/" in u
                   or (re.search(r"cesgranrio", u, re.I) and re.search(r"download|arquivo|documento|edital|file", u, re.I)
                       and not re.search(r"^/(concurso/|page_category/|concursos)", urlparse(u).path)))
            if doc and u not in vistos and not re.search(r"\.(png|jpe?g|gif|svg|webp|css|js)($|\?)", u, re.I):
                vistos.add(u)
                out.append((u, rot))
        # URLs de PDF soltas em scripts/atributos (listas montadas por JavaScript)
        for u in re.findall(r'https?:\\?/\\?/[^"\'\s<>]+?\.pdf', html, re.I):
            u = u.replace("\\/", "/")
            if u not in vistos:
                vistos.add(u)
                out.append((u, ""))
        return out

    def listar_certames(self, ano: int) -> list[Certame]:
        self.diag = []
        try:
            certames_site = self._certames_site()
        except Bloqueado:
            certames_site = {}
        if not certames_site:                         # site oficial bloqueado (nuvem): sites especializados
            self.fonte = "sites especializados"
            return super().listar_certames(ano)
        self.fonte = "site oficial"
        saida, vistos = [], set()
        # certames com o ano no endereço primeiro (ex.: policia-civil-amapa-2026)
        for url, titulo in sorted(certames_site.items(), key=lambda x: 0 if str(ano) in x[0] else 1):
            d = {"certame": url, "links": 0, "candidatos": [], "verificados": []}
            self.diag.append(d)
            try:
                html = self.acesso.html(url, self.chave)
            except Bloqueado as e:
                d["erro"] = f"bloqueado: {e}"
                continue
            links = self._links_documentos(url, html)
            if not links:                             # conteúdo pode vir só pela API do WordPress
                slug = url.rstrip("/").rsplit("/", 1)[-1]
                for tipo in ("concurso", "pages", "posts"):
                    try:
                        lote = json.loads(self.acesso.texto(f"{BASE}/wp-json/wp/v2/{tipo}?slug={slug}", self.chave))
                    except (Bloqueado, ValueError):
                        continue
                    if isinstance(lote, list) and lote:
                        links = self._links_documentos(url, lote[0].get("content", {}).get("rendered", ""))
                        if links:
                            break
            d["links"] = len(links)
            pdfs = []
            for href, rot in links:
                # o filtro de "não é edital" vale só para o rótulo; "abertura" sempre passa
                if rot and _NAO_EDITAL.search(rot) and not re.search(r"abertura", rot, re.I):
                    continue
                pdfs.append((href, rot))
            # abertura > edital > demais; até 8 documentos por certame
            pdfs.sort(key=lambda x: 0 if re.search(r"abertura", x[1], re.I) else 1 if re.search(r"edital", x[1], re.I) else 2)
            d["candidatos"] = [f"{r} | {h}" for h, r in pdfs[:8]]
            for href, rot in pdfs[:8]:
                doc = Documento(rot or "Edital", href, "edital")
                try:
                    self.acesso.baixar(doc, self.chave)
                    ok, data, pags = verificar(doc.caminho_local, self.banca_regex, ano)
                except Exception as e:
                    d["verificados"].append(f"{href} → erro {e.__class__.__name__}")
                    continue
                d["verificados"].append(f"{href} → {'ok' if ok else 'não é edital de ' + str(ano)} ({data})")
                if not ok or doc.sha256 in vistos:
                    continue
                vistos.add(doc.sha256)
                doc.publicado_em = data
                orgao, _ = campos.orgao_do_edital(pags, doc.titulo, href)
                c = Certame("cesgranrio", url.rstrip("/").rsplit("/", 1)[-1], url, titulo=titulo or rot,
                            orgao=orgao or "", publicado_em=data or date(ano, 1, 1), documentos=[doc])
                c.extra["oficial"] = True
                saida.append(c)
                break
        return saida
