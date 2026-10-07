"""Adaptador Instituto AOCP.

Diagnóstico de 07/10/2026 (rede da FGV): HTTP simples abre o site e a API; pelo navegador o Cloudflare barra.
Na nuvem, tudo bloqueia a partir da 2ª página. Por isso:
  1) site oficial por HTTP simples (funciona no computador da FGV):
     - lista:   GET {base}/api/concursos?status=<SUBSCRIBE|IN_PROGRESS|RESULTS_AVAILABLE|FINISHED|NEWS>
                (endpoint usado pelo próprio site — chunk Next.js app/concursos/status/[status])
     - certame: GET https://link.institutoaocp.org.br/api/concursos/{id} → "publicacoes" com data no nome
                ("30/07/2026 - Edital de Abertura (Retificado em 16/09/2026) - …"), PDFs em arquivos-site (oficial)
  2) se o site oficial bloquear: sites especializados (bancas/noticias.py), autorizado em 06/10/2026.

Teste na rede da FGV (07/10/2026): a API devolve a lista e o detalhe (30 certames de 2026), mas o servidor dos PDFs
(arquivos-site.institutoaocp.org.br) tem robots.txt "Disallow: /" — o PDF oficial não é lido. Para cada certame da
lista oficial, o edital é procurado como cópia em site especializado (matéria do Gran com o nome do órgão) e só é
aceito se o PDF se identifica como edital de abertura do Instituto AOCP, do ano pedido, e do mesmo órgão. Sem cópia,
o certame vai para PENDENTES com "EDITAL NÃO LOCALIZADO" (órgão e data vêm da lista oficial).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

import normalizacao as N
from bancas.base import Adaptador, Bloqueado
from bancas.noticias import AdaptadorNoticias, copia_edital
from extracao import campos, pdf
from modelos import Certame, Documento

API_CERTAME = "https://link.institutoaocp.org.br/api/concursos/{id}"
BASES_LISTA = ["https://link.institutoaocp.org.br/api/concursos", "https://www.institutoaocp.org.br/api/concursos"]
STATUS = ["NEWS", "NEW", "SUBSCRIBE", "SUBSCRIBES_OPEN", "IN_PROGRESS", "RESULTS_AVAILABLE", "RESULT_AVAILABLE", "FINISHED"]


def _data_pub(nome: str) -> date | None:
    m = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})", nome)
    return datetime.strptime("/".join(m.groups()), "%d/%m/%Y").date() if m else None


class Aocp(AdaptadorNoticias, Adaptador):
    chave = "aocp"
    inicio = "https://link.institutoaocp.org.br/api/concursos"
    banca_regex = r"INSTITUTO AOCP|\bAOCP\b"
    termos = ["Instituto AOCP edital publicado", "AOCP edital", "AOCP banca edital"]

    def _json(self, url):
        return json.loads(self.acesso.texto(url, self.chave))

    # ------------------------------------------------------------------ site oficial
    def _ids_oficiais(self) -> list[str]:
        ids: dict[str, None] = {}
        for base in BASES_LISTA:
            achou = False
            for st in STATUS:
                try:
                    lote = self._json(f"{base}?status={st}")
                except (Bloqueado, ValueError):
                    continue
                for c in lote if isinstance(lote, list) else lote.get("content", []) if isinstance(lote, dict) else []:
                    # pré-filtro por ano: se o item da lista só cita anos anteriores, nem consulta o detalhe
                    anos = [int(a) for a in re.findall(r"\b(20\d{2})\b", json.dumps(c, ensure_ascii=False))]
                    if anos and max(anos) < self._ano:
                        achou = True
                        continue
                    # a URL pública usa o código do concurso (ex.: 706); o JSON pode trazê-lo com nomes diferentes
                    for k in ("idConcurso", "codigo", "concurso", "id"):
                        if str(c.get(k, "")).isdigit():
                            ids[str(c[k])] = None
                            break
                    achou = True
            if achou:
                break
        return list(ids)

    def listar_certames(self, ano: int) -> list[Certame]:
        self._ano = ano
        self._usados: set[str] = set()
        try:
            ids = self._ids_oficiais()
        except Bloqueado:
            ids = []
        if not ids:                                   # site oficial bloqueado ou lista indisponível
            self.fonte = "sites especializados"
            return super().listar_certames(ano)
        self.fonte = "site oficial"
        saida, antigos = [], 0
        # códigos crescem com o tempo: do mais novo para o mais antigo; 15 certames seguidos de anos anteriores encerram
        for i in sorted(ids, key=int, reverse=True):
            if antigos >= 15:
                break
            try:
                det = self._json(API_CERTAME.format(id=i))
            except (Bloqueado, ValueError):
                continue
            det = det[0] if isinstance(det, list) and det else det
            if not isinstance(det, dict):
                continue
            pubs = det.get("publicacoes") or []
            ab = [p for p in pubs if re.search(r"edital de abertura", p.get("nome", ""), re.I)
                  and not re.search(r"^\s*\d{2}/\d{2}/\d{4}\s*-\s*retifica", p.get("nome", ""), re.I)]
            datas = [d for d in (_data_pub(p["nome"]) for p in ab) if d]
            if datas and min(datas).year < ano:
                antigos += 1
            elif datas:
                antigos = 0
            if not datas or min(datas).year != ano:
                continue
            # versão retificada/consolidada mais recente prevalece
            ab.sort(key=lambda p: _data_pub(p["nome"]) or date.min)
            cons = [p for p in ab if re.search(r"retificad|consolidad|atualizad", p["nome"], re.I)]
            alvo = (cons or ab)[-1] if cons else ab[0]
            c = Certame("aocp", i, f"https://www.institutoaocp.org.br/concursos/{i}",
                        titulo=(det.get("chamada") or det.get("nome") or "").strip(), publicado_em=min(datas),
                        tipo="processo_seletivo" if re.search(r"seletiv", det.get("tipoProcesso", ""), re.I) else "concurso")
            c.orgao = (det.get("nome") or "").strip()
            c.extra["oficial"] = True
            oficial = Documento(alvo["nome"], alvo["url"], "edital", _data_pub(alvo["nome"]))
            c.documentos = [oficial] if self.acesso.permitido(alvo["url"]) else self._copia(c, ano)
            saida.append(c)
        return saida

    def _copia(self, c: Certame, ano: int) -> list[Documento]:
        partes = [x.strip() for x in re.split(r"\s+[-–]\s+", c.orgao) if x.strip()]
        nome = partes[0] if partes else c.orgao
        # termos: sigla/1ª parte; nome por extenso; "Prefeitura de X"
        termos = [nome] + [x for x in partes[1:] if len(x) > 3][:1]
        termos += [re.sub(r"^PREFEITURA MUNICIPAL DE\s+", "Prefeitura de ", c.orgao, flags=re.I)] if re.match(r"PREFEITURA", c.orgao, re.I) else []
        ref = max(partes, key=len) if partes else c.orgao
        return copia_edital(self, ref, termos, "AOCP", ano, self._usados, ("arquivos-site.institutoaocp.org.br",))

    def listar_documentos(self, certame):
        return certame.documentos
