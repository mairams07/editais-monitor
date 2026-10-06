"""Adaptador FCC.

Padrão observado (a confirmar na Etapa 0 — rede deste ambiente ainda bloqueada em 06/10/2026):
Página do certame: concursosfcc.com.br/concursos/{slug}/index.html. robots.txt bloqueou leitura automatizada em teste anterior.
"""
from __future__ import annotations

from bancas.base import Adaptador
from modelos import Certame, Documento


class Fcc(Adaptador):
    chave = "fcc"
    inicio = "https://www.concursosfcc.com.br/"

    def listar_certames(self, ano: int) -> list[Certame]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")

    def listar_documentos(self, certame: Certame) -> list[Documento]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")
