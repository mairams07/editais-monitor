"""Adaptador Vunesp.

Etapa 0 (06/10/2026): HTTP simples recebe 403 (Akamai) em todo o domínio, inclusive documentos; navegador real abre.
  - listas: /busca/{concurso|vestibular|avaliacao}/{inscricoes abertas|proximo|em andamento|encerrados}, com botão
    "mostrar mais opções" (6 por vez). Código do certame traz o ano: PMES2601 = 2026.
  - certame: /{CÓDIGO}, aba "EDITAIS E DOCUMENTOS" (lista com data) → documento.vunesp.com.br/documento/stream/{id}
Data de publicação = data do item "Edital de Abertura".
"""
from __future__ import annotations

import re
from datetime import date, datetime

import normalizacao as N
from bancas.base import Adaptador
from extracao import campos, pdf
from modelos import Certame, Documento

BASE = "https://www.vunesp.com.br"
CATS = [f"{t}/{s}" for t in ("concurso", "vestibular", "avaliacao")
        for s in ("inscricoes%20abertas", "proximo", "em%20andamento", "encerrados")]


class Vunesp(Adaptador):
    chave = "vunesp"
    inicio = BASE

    def _codigos(self, cat: str, yy: set[str]) -> dict:
        pg = self.acesso.ir(f"{BASE}/busca/{cat}", self.chave)
        anterior = -1
        for _ in range(80):
            cods = set(re.findall(r'"/([A-Z]{3,5}\d{4})"', pg.content()))
            if len(cods) == anterior:
                break
            anterior = len(cods)
            mais = pg.get_by_text(re.compile("mostrar mais", re.I))
            if not mais.count():
                break
            mais.first.click()
            pg.wait_for_timeout(2500)
        return {c: cat.split("/")[0] for c in cods if c[-4:-2] in yy}

    def listar_certames(self, ano: int) -> list[Certame]:
        yy = {str(ano)[-2:], str(ano - 1)[-2:]}
        cods: dict = {}
        for cat in CATS:
            cods.update(self._codigos(cat, yy))
        saida = []
        for cod, tipo in sorted(cods.items()):
            pg = self.acesso.ir(f"{BASE}/{cod}", self.chave)
            titulo = " ".join(pg.title().split("|")[0].split())
            try:
                pg.get_by_text("EDITAIS E DOCUMENTOS").first.click()
                pg.wait_for_timeout(4000)
            except Exception:
                continue
            itens = pg.eval_on_selector_all(
                "a[href*='documento/stream']",
                "els=>els.map(e=>[e.href,(e.closest('li,tr,div')||e).innerText.replace(/\\s+/g,' ').trim()])")
            ab = []
            for href, txt in itens:
                if "rybena" in href or not re.search(r"edital de abertura|abertura de inscri", txt, re.I):
                    continue
                m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
                d = date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
                ab.append((d, href, txt[:150]))
            ab = [x for x in ab if x[0]]
            if not ab or min(x[0] for x in ab).year != ano:
                continue
            ab.sort()
            c = Certame("vunesp", cod, f"{BASE}/{cod}", titulo=titulo, publicado_em=ab[0][0],
                        tipo={"vestibular": "vestibular_exame", "avaliacao": "vestibular_exame"}.get(tipo, "concurso"))
            # retificado/consolidado mais recente prevalece
            cons = [x for x in ab if re.search(r"retificad|consolidad|atualizad", x[2], re.I)]
            d, href, txt = (cons or ab)[-1] if cons else ab[0]
            c.extra["docs"] = [Documento(txt, href, "edital", d)]
            saida.append(c)
        return saida

    def listar_documentos(self, certame: Certame) -> list[Documento]:
        return certame.extra.get("docs", [])

    def baixar(self, doc: Documento) -> Documento:
        return self.acesso.baixar_navegador(doc, self.chave)

    def extrair(self, certame: Certame) -> None:
        ed = certame.documentos[0]
        pags = pdf.ler(ed.caminho_local)
        campos.preencher_certame(certame, pags, ed.titulo, ed.url)
