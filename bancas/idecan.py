"""Adaptador IDECAN.

Padrão observado (a confirmar na Etapa 0 — rede deste ambiente ainda bloqueada em 06/10/2026):
idecan.org.br / concurso.idecan.org.br; devolveu 403 em teste anterior.
"""
from __future__ import annotations

from bancas.base import Adaptador
from modelos import Certame, Documento


class Idecan(Adaptador):
    chave = "idecan"
    inicio = "https://www.idecan.org.br/"

    def listar_certames(self, ano: int) -> list[Certame]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")

    def listar_documentos(self, certame: Certame) -> list[Documento]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")
