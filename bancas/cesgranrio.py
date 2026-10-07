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
from bancas.noticias import AdaptadorNoticias, _NAO_EDITAL, copia_edital, verificar
from extracao import campos
from modelos import Certame, Documento

BASE = "https://www.cesgranrio.org.br"


_RODAPE = re.compile(r"c[óo]digo[- ]de[- ][ée]tica|integridade|privacidade|cookies|informe[- ]de[- ]rendimentos", re.I)


class Cesgranrio(AdaptadorNoticias, Adaptador):
    chave = "cesgranrio"
    inicio = BASE + "/concursos/"
    banca_regex = r"CESGRANRIO"
    termos = ["Cesgranrio edital publicado", "Fundação Cesgranrio edital", "Cesgranrio banca edital"]

    def _certames_site(self) -> dict[str, str]:
        """{url do certame: título}. Tenta a API do WordPress; cai para as páginas de lista."""
        out: dict[str, str] = {}
        self._datas: dict[str, str] = {}
        try:
            lote = json.loads(self.acesso.texto(f"{BASE}/wp-json/wp/v2/concurso?per_page=100&_fields=link,title,date", self.chave))
            if isinstance(lote, list):
                for p in lote:
                    out[p["link"]] = re.sub(r"<[^>]+>", "", p.get("title", {}).get("rendered", ""))
                    self._datas[p["link"]] = (p.get("date") or "")[:10]
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
            if not rot or re.fullmatch(r"(?:acesse|clique)\s+aqui|download|baixar|ver|abrir", rot, re.I):
                # "Acesse aqui" sob o título "Cronograma": o rótulo útil é o título da seção
                ant = a.find_previous(string=lambda t: t and t.strip() and t.strip() != rot)
                rot = (ant.strip()[:120] if ant else "") + (f" ({rot})" if rot else "")
            doc = (re.search(r"\.pdf($|[?#])", u, re.I) or "/wp-content/uploads/" in u
                   or (re.search(r"cesgranrio", u, re.I) and re.search(r"download|arquivo|documento|edital|file", u, re.I)
                       and not re.search(r"^/(concurso/|page_category/|concursos)", urlparse(u).path)))
            base = u.split("?")[0]
            if doc and base not in vistos and not re.search(r"\.(png|jpe?g|gif|svg|webp|css|js)($|\?)", u, re.I):
                vistos.add(base)                      # mesmo PDF com e sem assinatura na URL: fica o 1º (assinado)
                out.append((u, rot))
        # URLs de PDF soltas em scripts/atributos (listas montadas por JavaScript)
        for u in re.findall(r'https?:\\?/\\?/[^"\'\s<>]+?\.pdf', html, re.I):
            u = u.replace("\\/", "/")
            if u.split("?")[0] not in vistos:
                vistos.add(u.split("?")[0])
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
            # página criada antes de julho do ano anterior não traz edital do ano pedido
            if self._datas.get(url) and self._datas[url] < f"{ano - 1}-07-01":
                d["erro"] = f"página de {self._datas[url]} — anterior ao período"
                continue
            try:
                html = self.acesso.html(url, self.chave)
            except Bloqueado as e:
                d["erro"] = f"bloqueado: {e}"
                html = ""                             # segue para o portal/cópia em site especializado
            # PDFs do rodapé, iguais em todas as páginas (Código de Ética, Integridade) não são do certame
            links = [(h, r) for h, r in self._links_documentos(url, html) if not _RODAPE.search(f"{r} {h}")]
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
            if not links:
                # teste de 07/10/2026: a página do certame só traz o resumo e o botão para o portal do candidato
                # (concursos.cesgranrio.org.br/portal/avaliacoes/{id}); os documentos ficam lá
                for portal in dict.fromkeys(re.findall(r"https://concursos\.cesgranrio\.org\.br/portal/avaliacoes/\d+", html)):
                    d["portal"] = portal
                    for dinamico in (False, True):
                        try:
                            ph = self.acesso.html(portal, self.chave, dinamico=dinamico)
                        except Bloqueado as e:
                            d.setdefault("erro_portal", []).append(f"{'navegador' if dinamico else 'http'}: {e}")
                            continue
                        links = self._links_documentos(portal, ph)
                        d.setdefault("portal_links", []).append(f"{'navegador' if dinamico else 'http'}: {len(links)}")
                        if links:
                            break
                    if links:
                        break
            d["links"] = len(links)
            pdfs = []
            # lista de aceitação pelo rótulo (portal do candidato, teste FGV 07/10/2026): "EDITAL Nº 001/2026 -
            # RETIFICADO", "EDITAL Nº 03 - TRANSPETRO/…". Fora: "EDITAL DE CONVOCAÇÃO/RESULTADO/SORTEIO", retificações
            # avulsas, cronograma, provas, gabaritos, e edital com outro ano no número (ex.: "CAIXA Nº 01/2025").
            def aceito(rot):
                if not re.search(r"\bEDITAL\b|\babertura\b", rot, re.I) or re.search(r"RETIFICA[ÇC][ÃA]O|ADITIVO", rot, re.I):
                    return False
                if re.search(r"EDITAL\s+D[EO]S?\s+(?:CONVOCA|RESULTADO|SORTEIO|HOMOLOGA|CLASSIFICA|LOCA)", rot, re.I):
                    return False
                anos = re.findall(r"/\s*((?:19|20)\d{2})\b", rot)
                return not anos or str(ano) in anos
            pdfs = [(h, r) for h, r in links if r and aceito(r)]
            if not pdfs:                              # sem rótulo útil: tenta os PDFs sem rótulo (conferidos pelo conteúdo)
                pdfs = [(h, r) for h, r in links if not r]
            # edital consolidado/retificado primeiro
            pdfs.sort(key=lambda x: 0 if re.search(r"RETIFICAD|CONSOLIDAD|ATUALIZAD", x[1], re.I) else 1)
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
                n_editais = len({re.search(r"N[º°o.]*\s*\d+", r).group(0) for _, r in pdfs
                                 if re.search(r"\bEDITAL\b\s*N[º°o.]*\s*\d+", r, re.I)})
                if n_editais <= 1:
                    break
                c.id_banca = f"{c.id_banca}#{len([x for x in saida if x.url == url])}"
            if any(x.url == url for x in saida):
                pass
            else:
                # sem PDF no site/portal: cópia do edital em site especializado, conferida pelo conteúdo
                nome = self._nome_do_titulo(titulo)
                # um certame pode ter vários editais de abertura (ex.: Transpetro 2026: editais 1 a 4)
                docs = copia_edital(self, nome, [nome, f"concurso {nome}"], "", ano, vistos, todos=True) if nome else []
                d["copia"] = [x.url for x in docs] or "não localizada"
                slug = url.rstrip("/").rsplit("/", 1)[-1]
                for k, doc in enumerate(docs, 1):
                    c = Certame("cesgranrio", slug if len(docs) == 1 else f"{slug}#{k}", url, titulo=titulo,
                                orgao=getattr(doc, "orgao_detectado", ""),
                                publicado_em=doc.publicado_em or date(ano, 1, 1), documentos=[doc])
                    c.extra["data_confirmada"] = doc.publicado_em is not None
                    saida.append(c)
        return saida

    @staticmethod
    def _nome_do_titulo(titulo: str) -> str:
        """'Concurso Polícia Civil do Amapá 2026' → 'Polícia Civil do Amapá'; 'Concurso EPPGG – Bahia 2026' → 'EPPGG Bahia'."""
        t = re.sub(r"&#\d+;|&\w+;", " ", titulo or "")
        t = re.sub(r"\b(?:Concurso|P[úu]blico|Processo Seletivo|Sele[çc][ãa]o)\b", " ", t, flags=re.I)
        t = re.sub(r"\b(?:19|20)\d{2}\b|\b\d+/\d{4}\b|[–—-]\s*$", " ", t)
        t = re.sub(r"\s+[–—]\s+", " ", t)
        return " ".join(t.split()).strip(" -–")
