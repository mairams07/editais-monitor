"""Adaptador Cebraspe.

Etapa 0 (06/10/2026): API JSON pública usada pelo próprio site.
  - lista:   https://apis.cebraspe.org.br/cebraspe/eventos/tipo/concursos/  (fases Novos/Abertas/Andamento/Encerrados)
  - evento:  https://apis.cebraspe.org.br/cebraspe/eventos/{slug}            (arquivosEdital com data e descrição)
  - arquivo: https://cdn.cebraspe.org.br/concursos/{slug}/arquivos/{nomeArquivo}
Data de publicação = data do arquivo "Edital nº 1 – Abertura". Se existir a versão "Atualizado conforme
retificações", ela é a lida (retificação mais recente prevalece).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

import normalizacao as N
from bancas.base import Adaptador
from extracao import campos, pdf
from modelos import Cargo, Certame, Documento, Evidencia

API = "https://apis.cebraspe.org.br/cebraspe/eventos"
CDN = "https://cdn.cebraspe.org.br/concursos"


def _data(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y %H:%M").date()
    except (ValueError, AttributeError):
        return None


class Cebraspe(Adaptador):
    chave = "cebraspe"
    inicio = f"{API}/tipo/concursos/"

    def _json(self, url):
        return json.loads(self.acesso.texto(url, self.chave))

    def listar_certames(self, ano: int) -> list[Certame]:
        saida = []
        for fase in self._json(self.inicio):
            for ev in fase["eventos"]:
                # eventoAno é o "ano do evento", não a data do edital: olha também o ano anterior
                if not ev.get("eventoAno") or ev["eventoAno"] < ano - 1:
                    continue
                det = self._json(f"{API}/{ev['eventoURL']}")
                datas = [_data(a["dataArquivo"]) for a in self._aberturas(det)]
                datas = [d for d in datas if d]
                if not datas or min(datas).year != ano:
                    continue
                c = Certame("cebraspe", ev["eventoURL"], f"https://www.cebraspe.org.br/concursos/{ev['eventoURL']}",
                            titulo=(det.get("eventoNomeCompleto") or ev["eventoNomeAbreviado"]).strip(),
                            publicado_em=min(datas), tipo=self._tipo(det))
                c.extra["det"] = det
                saida.append(c)
        return saida

    @staticmethod
    def _aberturas(det):
        return [a for a in det.get("arquivosEdital") or []
                if a["tipoExtensaoArquivo"] == "_.pdf" and re.search(r"abertura", a["descricaoArquivo"], re.I)]

    @staticmethod
    def _tipo(det):
        nome = N.texto(det.get("eventoNomeAbreviado"))
        if re.search(r"ESTAGI|SELE|PSE\b|ACOLHEDORA", nome):
            return "processo_seletivo"
        if "RESIDENCIA" in nome:
            return "residencia"
        if re.search(r"EXAME|VESTIBULAR|CERTIFICA", nome):
            return "vestibular_exame"
        return "concurso"

    def listar_documentos(self, certame: Certame) -> list[Documento]:
        det = certame.extra.get("det") or self._json(f"{API}/{certame.id_banca}")
        docs = []
        for a in det.get("arquivosEdital") or []:
            if a["tipoExtensaoArquivo"] != "_.pdf":
                continue
            d = a["descricaoArquivo"].strip()
            if re.search(r"abertura", d, re.I):
                tipo = "consolidado" if re.search(r"atualizado|consolidad", d, re.I) else "edital"
            elif re.search(r"retifica", d, re.I):
                tipo = "retificacao"
            else:
                continue
            docs.append(Documento(d, f"{CDN}/{certame.id_banca}/arquivos/{a['nomeArquivo']}", tipo, _data(a["dataArquivo"])))
        docs.sort(key=lambda d: d.publicado_em or date.min)
        # Lê só o necessário: o edital consolidado mais recente; sem ele, o original (retificações vão ao LOG)
        cons = [d for d in docs if d.tipo == "consolidado"]
        if cons:
            cons[-1].tipo = "edital"
            return [cons[-1]]
        return [d for d in docs if d.tipo == "edital"][:1]

    # ------------------------------------------------------------------ extração
    def extrair(self, certame: Certame) -> None:
        ed = next(d for d in certame.documentos if d.tipo == "edital")
        pags = pdf.ler(ed.caminho_local)
        campos.preencher_certame(certame, pags, ed.titulo, ed.url,
                                 uf_reserva=next((t for t in certame.id_banca.split("_") if t in N.UFS), ""))
