"""Estruturas de dados compartilhadas entre adaptadores, extração e gravação."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

STATUS = ("CONFIRMADO", "INDÍCIO", "NÃO LOCALIZADO", "EDITAL NÃO LOCALIZADO", "BLOQUEADO", "INCONSISTÊNCIA")


@dataclass
class Evidencia:
    """Um valor extraído, com rastreabilidade obrigatória."""
    valor: Any
    status: str
    documento: str = ""
    pagina: int | None = None
    trecho: str = ""          # literal, até 30 palavras
    url: str = ""
    verificado_em: date = field(default_factory=date.today)

    def __post_init__(self):
        if self.status not in STATUS:
            raise ValueError(f"status inválido: {self.status}")
        palavras = self.trecho.split()
        if len(palavras) > 30:
            self.trecho = " ".join(palavras[:30]) + " …"


@dataclass
class Documento:
    titulo: str
    url: str
    tipo: str = "outro"       # edital | retificacao | inscritos | outro
    publicado_em: date | None = None
    sha256: str | None = None
    caminho_local: str | None = None
    copia_terceiro: bool = False


@dataclass
class Cargo:
    nome: str
    especialidade: str = ""
    campos: dict[str, Evidencia] = field(default_factory=dict)  # chave = coluna canônica


@dataclass
class Certame:
    banca: str                # nome canônico (ver normalizacao.BANCAS)
    id_banca: str             # slug/código do certame no site da banca
    url: str
    titulo: str = ""
    orgao: str = ""
    uf: str = ""
    publicado_em: date | None = None
    tipo: str = ""            # concurso | processo_seletivo | residencia | vestibular_exame
    documentos: list[Documento] = field(default_factory=list)
    cargos: list[Cargo] = field(default_factory=list)
    campos_certame: dict[str, Evidencia] = field(default_factory=dict)  # valem para todos os cargos
    extra: dict = field(default_factory=dict)  # dados brutos do adaptador (não vão para a planilha)
