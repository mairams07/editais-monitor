"""Adaptador Instituto AOCP.

Padrão observado (a confirmar na Etapa 0 — rede deste ambiente ainda bloqueada em 06/10/2026):
institutoaocp.org.br/concursos/{id}; conteúdo carregado dinamicamente (usar navegador).
"""
from __future__ import annotations

from bancas.base import Adaptador
from modelos import Certame, Documento


class Aocp(Adaptador):
    chave = "aocp"
    inicio = "https://www.institutoaocp.org.br/concursos"

    def listar_certames(self, ano: int) -> list[Certame]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")

    def listar_documentos(self, certame: Certame) -> list[Documento]:
        raise NotImplementedError("estrutura do site ainda não confirmada (Etapa 0)")
