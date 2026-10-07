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
from urllib.parse import urljoin

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

    def listar_certames(self, ano: int) -> list[Certame]:
        try:
            certames_site = self._certames_site()
        except Bloqueado:
            certames_site = {}
        if not certames_site:                         # site oficial bloqueado (nuvem): sites especializados
            self.fonte = "sites especializados"
            return super().listar_certames(ano)
        self.fonte = "site oficial"
        saida, vistos = [], set()
        for url, titulo in certames_site.items():
            try:
                html = self.acesso.html(url, self.chave)
            except Bloqueado:
                continue
            pdfs = []
            for href, txt in re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.I | re.S):
                rot = re.sub(r"<[^>]+>|\s+", " ", txt).strip()
                if _NAO_EDITAL.search(rot + " " + href.rsplit("/", 1)[-1]):
                    continue
                pdfs.append((urljoin(url, href), rot))
            # rótulo com "edital"/"abertura" primeiro; no máximo 5 PDFs por certame
            pdfs.sort(key=lambda x: 0 if re.search(r"abertura|edital", x[1], re.I) else 1)
            for href, rot in pdfs[:5]:
                doc = Documento(rot or "Edital", href, "edital")
                try:
                    self.acesso.baixar(doc, self.chave)
                    ok, data, pags = verificar(doc.caminho_local, self.banca_regex, ano)
                except Exception:
                    continue
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
