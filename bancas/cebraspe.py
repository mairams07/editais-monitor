"""Adaptador Cebraspe.

Padrão observado (a confirmar na Etapa 0 — rede deste ambiente ainda bloqueada em 06/10/2026):
Página do certame: cebraspe.org.br/concursos/{slug}; PDFs em cdn.cebraspe.org.br/concursos/{slug}/arquivos/{hash}.pdf; editais 'Ed_1_…'; procurar 'relação provisória/final de inscritos'.
"""
from __future__ import annotations

from bancas.base import Adaptador
from modelos import Certame, Documento


class Cebraspe(Adaptador):
    chave = "cebraspe"
    inicio = "https://www.cebraspe.org.br/concursos"

    def listar_certames(self, ano: int) -> list[Certame]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")

    def listar_documentos(self, certame: Certame) -> list[Documento]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")
