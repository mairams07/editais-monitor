"""Leitura (somente leitura) e gravação em cópia da CONCORRENTES_FGV.xlsx."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from copy import copy
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill

import normalizacao as N
from modelos import Evidencia

VERDE = PatternFill("solid", fgColor="C6EFCE")     # CONFIRMADO
AMARELO = PatternFill("solid", fgColor="FFEB9C")   # INDÍCIO (FFFF00 é da equipe — não usar)

LOG_COLUNAS = ["CÓD_INTERNO", "coluna", "valor anterior", "valor proposto", "status", "documento", "página",
               "trecho", "URL", "data da verificação", "linha", "ação"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


# ------------------------------------------------------------------ entrada
def preparar_entrada(cfg: dict, base: Path) -> tuple[Path, bool]:
    """Copia a planilha sincronizada para entrada/ com data e hora (nunca lê o original diretamente).

    Devolve (cópia, mudou_desde_ultima_execucao)."""
    entrada = base / cfg["planilha"]["entrada_dir"]
    entrada.mkdir(parents=True, exist_ok=True)
    origem = cfg["planilha"].get("caminho_sincronizado") or ""
    if origem and Path(origem).exists():
        destino = entrada / f"CONCORRENTES_FGV_{datetime.now():%Y-%m-%d_%H%M%S}.xlsx"
        shutil.copy2(origem, destino)
    else:
        copias = sorted(entrada.glob("CONCORRENTES_FGV*.xlsx"), key=lambda p: p.stat().st_mtime)
        if not copias:
            raise FileNotFoundError("Planilha não encontrada: configure caminho_sincronizado ou coloque a cópia em entrada/")
        destino = copias[-1]
    estado = base / cfg["estado_dir"] / "entrada.json"
    estado.parent.mkdir(parents=True, exist_ok=True)
    anterior = json.loads(estado.read_text()) if estado.exists() else {}
    atual = sha256(destino)
    estado.write_text(json.dumps({"arquivo": destino.name, "sha256": atual, "em": datetime.now().isoformat()}))
    return destino, anterior.get("sha256") != atual


# ------------------------------------------------------------------ leitura
@dataclass
class Aba:
    nome: str
    linha_cabecalho: int
    colunas: dict[str, int]                         # coluna canônica → índice 1-based
    linhas: list[tuple[int, dict]] = field(default_factory=list)  # (nº da linha, {coluna canônica: valor})

    @property
    def ultima_linha_dados(self) -> int:
        return max((n for n, _ in self.linhas), default=self.linha_cabecalho)


def detectar_cabecalho(ws, max_busca: int = 10) -> int:
    """Linha onde aparecem BANCA VENCEDORA e CLIENTE. Nunca assume posição fixa."""
    for r in range(1, max_busca + 1):
        canon = {N.coluna(c.value) for c in ws[r]}
        if {"BANCA", "CLIENTE"} <= canon:
            return r
    raise ValueError(f"Cabeçalho não encontrado na aba {ws.title}")


def ler_aba(caminho: Path, nome: str) -> Aba:
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    ws = wb[nome]
    hr = detectar_cabecalho(ws)
    cab = next(ws.iter_rows(min_row=hr, max_row=hr, values_only=True))
    colunas = {}
    for i, v in enumerate(cab, start=1):
        c = N.coluna(v)
        if c and c not in colunas:
            colunas[c] = i
    aba = Aba(nome, hr, colunas)
    for n, row in enumerate(ws.iter_rows(min_row=hr + 1, values_only=True), start=hr + 1):
        if not any(not N.vazio(v) for v in row):
            continue
        aba.linhas.append((n, {c: row[i - 1] if i - 1 < len(row) else None for c, i in colunas.items()}))
    wb.close()
    return aba


def avisos_de_preservacao(caminho: Path) -> list[str]:
    """Recursos que o openpyxl descarta ao salvar — vão para o relatório."""
    avisos = []
    with zipfile.ZipFile(caminho) as z:
        nomes = z.namelist()
    if any("threadedComments" in n for n in nomes):
        avisos.append("Comentários encadeados (threaded comments) serão descartados na cópia de saída; "
                      "o original não é alterado.")
    if any(n.startswith("xl/vbaProject") for n in nomes):
        avisos.append("Macros VBA presentes: a cópia de saída é .xlsx sem macros.")
    if any("slicer" in n.lower() for n in nomes):
        avisos.append("Segmentações de dados (slicers) serão descartadas na cópia de saída.")
    return avisos


# ------------------------------------------------------------------ gravação
@dataclass
class LinhaNova:
    """Linha EXTERNO a inserir: coluna canônica → (valor, Evidencia | None)."""
    celulas: dict[str, tuple[object, Evidencia | None]]
    chave_certame: str            # banca:id — para o LOG


def _valor_celula(v):
    if isinstance(v, Decimal):
        return float(v)
    return v


FORMATO = {"SALARIO": "#,##0.00", "TAXA": "#,##0.00", "VALOR_GLOBAL": '"R$"\\ #,##0.00'}


def gravar(entrada: Path, aba_nome: str, novas: list[LinhaNova], log: list[dict], extras: dict[str, list[dict]],
           saida_dir: Path, hoje: date | None = None) -> tuple[Path, Path]:
    """Gera saida/CONCORRENTES_FGV_atualizado_{data}.xlsx e saida/ALTERACOES_{data}.xlsx."""
    hoje = hoje or date.today()
    saida_dir.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(entrada)                     # completo: preserva estilos, fórmulas, filtros
    ws = wb[aba_nome]
    aba = ler_aba(entrada, aba_nome)
    cols = aba.colunas
    modelo = aba.ultima_linha_dados                          # copia estilo da última linha existente
    r = aba.ultima_linha_dados + 1
    alteracoes = []
    for ln in novas:
        for c, idx in cols.items():
            dst, src = ws.cell(r, idx), ws.cell(modelo, idx)
            dst.font, dst.border, dst.alignment = copy(src.font), copy(src.border), copy(src.alignment)
            dst.number_format = FORMATO.get(c, src.number_format)
        for c, (valor, ev) in ln.celulas.items():
            if c not in cols or N.vazio(valor):
                continue
            cel = ws.cell(r, cols[c])
            cel.value = _valor_celula(valor)
            if ev is not None:
                cel.fill = VERDE if ev.status == "CONFIRMADO" else AMARELO
            log.append(_log(ln, c, valor, ev, r, "INCLUÍDO (EXTERNO)"))
            alteracoes.append({"aba": aba_nome, "linha": r, "certame": ln.chave_certame, "coluna": c,
                               "valor": _valor_celula(valor), "status": ev.status if ev else "",
                               "fonte": (ev.url or ev.documento) if ev else ""})
        r += 1

    _aba_tabela(wb, "LOG", LOG_COLUNAS, [[d.get(k) for k in LOG_COLUNAS] for d in log], anexar=True)
    for nome, linhas in extras.items():
        if linhas:
            cab = list(linhas[0].keys())
            _aba_tabela(wb, nome, cab, [[d.get(k) for k in cab] for d in linhas], anexar=False)

    arq = saida_dir / f"CONCORRENTES_FGV_atualizado_{hoje:%Y-%m-%d}.xlsx"
    wb.save(arq)

    alt = openpyxl.Workbook()
    a = alt.active
    a.title = "ALTERACOES"
    cab = ["aba", "linha", "certame", "coluna", "valor", "status", "fonte"]
    a.append(cab)
    for d in sorted(alteracoes, key=lambda d: (d["aba"], d["linha"])):
        a.append([d[k] for k in cab])
    arq_alt = saida_dir / f"ALTERACOES_{hoje:%Y-%m-%d}.xlsx"
    alt.save(arq_alt)
    return arq, arq_alt


def _log(ln: LinhaNova, coluna: str, valor, ev: Evidencia | None, linha: int, acao: str) -> dict:
    return {"CÓD_INTERNO": ln.chave_certame, "coluna": coluna, "valor anterior": None,
            "valor proposto": _valor_celula(valor), "status": ev.status if ev else "",
            "documento": ev.documento if ev else "", "página": ev.pagina if ev else None,
            "trecho": ev.trecho if ev else "", "URL": ev.url if ev else "",
            "data da verificação": (ev.verificado_em if ev else date.today()).isoformat(), "linha": linha, "ação": acao}


def _aba_tabela(wb, nome: str, cab: list[str], linhas: list[list], anexar: bool):
    if nome in wb.sheetnames and anexar:
        ws = wb[nome]
    else:
        if nome in wb.sheetnames:
            del wb[nome]
        ws = wb.create_sheet(nome)
        ws.append(cab)
    for l in linhas:
        ws.append(l)
