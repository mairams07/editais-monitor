"""Adaptador Cesgranrio.

Padrão observado (a confirmar na Etapa 0 — rede deste ambiente ainda bloqueada em 06/10/2026):
Seção de concursos; PDFs por certame. Estrutura a confirmar.
"""
from __future__ import annotations

from bancas.base import Adaptador
from modelos import Certame, Documento


class Cesgranrio(Adaptador):
    chave = "cesgranrio"
    inicio = "https://www.cesgranrio.org.br/"

    def listar_certames(self, ano: int) -> list[Certame]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")

    def listar_documentos(self, certame: Certame) -> list[Documento]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")
