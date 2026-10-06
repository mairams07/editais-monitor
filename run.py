"""Execução: lista certames 2026 das 7 bancas, descarta os que já estão na planilha e inclui os demais como EXTERNO.

Uso:
  python run.py                 # execução completa
  python run.py --banca aocp    # só uma banca
  python run.py --dry-run       # não grava planilha; só relatório
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path

import yaml

import casamento
import montagem
import normalizacao as N
import planilha
from bancas import ADAPTADORES
from bancas.base import Acesso, Bloqueado
from extracao import campos, pdf
from modelos import Cargo, Certame, Evidencia

BASE = Path(__file__).resolve().parent


def extrair_generico(certame: Certame) -> None:
    """Preenche certame.cargos e certame.campos_certame a partir dos PDFs baixados.
    A retificação mais recente prevalece: documentos são lidos em ordem e valores posteriores substituem os anteriores."""
    cargos: dict[tuple, Cargo] = {}
    for doc in [d for d in certame.documentos if d.tipo in ("edital", "retificacao") and d.caminho_local]:
        pags = pdf.ler(doc.caminho_local)
        nome = doc.titulo + (" (cópia do PDF oficial)" if doc.copia_terceiro else "")
        for reg in campos.tabela_cargos(pags, nome, doc.url):
            k = (N.texto(reg["cargo"]), N.texto(reg.get("especialidade")))
            c = cargos.setdefault(k, Cargo(reg["cargo"], reg.get("especialidade", "")))
            ev = lambda v: Evidencia(v, "CONFIRMADO", nome, reg["pagina"], reg["trecho"], doc.url)
            for chave, col in (("vagas", "VAGAS"), ("vagas_cr", "VAGAS_CR"), ("salario", "SALARIO"), ("nivel", "NIVEL")):
                if reg.get(chave) is not None:
                    c.campos[col] = ev(reg[chave])
            if reg.get("inconsistencia"):
                c.campos["VAGAS"] = Evidencia(None, "INCONSISTÊNCIA", nome, reg["pagina"],
                                              f"INCONSISTÊNCIA NO EDITAL: {reg['inconsistencia']}", doc.url)
        taxas = campos.taxa(pags, nome, doc.url)
        if len({t.valor for t in taxas}) == 1:
            certame.campos_certame["TAXA"] = taxas[0]
        elif taxas:  # taxa varia por nível: atribui por nível do cargo quando o adaptador souber; aqui só registra
            certame.campos_certame["_TAXAS"] = taxas
        for fn, col in ((campos.etapas, "ETAPAS"), (campos.cidades, "CIDADES")):
            ev = fn(pags, nome, doc.url)
            if ev:
                certame.campos_certame[col] = ev
    if certame.uf:
        certame.campos_certame.setdefault("UF", Evidencia(certame.uf, "CONFIRMADO", url=certame.url,
                                                         trecho="UF do órgão na página do certame"))
    certame.cargos = list(cargos.values())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--banca", action="append", help="limita a execução a esta(s) banca(s)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", default=str(BASE / "config.yaml"))
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(open(a.config))
    hoje = date.today()
    ano = cfg["escopo"]["ano_publicacao"]

    entrada, mudou = planilha.preparar_entrada(cfg, BASE)
    abas = [planilha.ler_aba(entrada, n) for n in cfg["planilha"]["abas_deduplicacao"]]
    avisos = planilha.avisos_de_preservacao(entrada)
    vistos_p = BASE / cfg["estado_dir"] / "vistos.json"
    vistos = json.loads(vistos_p.read_text()) if vistos_p.exists() else {}

    acesso = Acesso(cfg["http"], BASE / cfg["estado_dir"] / "cache")
    rel = defaultdict(Counter)
    novas, log, pendentes, ja, falhas = [], [], [], [], []
    for chave in a.banca or cfg["bancas_ativas"]:
        ad = ADAPTADORES[chave](acesso)
        try:
            certames = [c for c in ad.listar_certames(ano) if c.publicado_em and c.publicado_em.year == ano]
        except NotImplementedError as e:
            falhas.append({"banca": N.BANCAS[chave], "url": ad.inicio, "motivo": f"adaptador pendente: {e}"})
            continue
        except Bloqueado as e:
            falhas.append({"banca": N.BANCAS[chave], "url": ad.inicio, "motivo": f"BLOQUEADO: {e}"})
            continue
        rel[chave]["certames_2026"] = len(certames)
        for cert in certames:
            res = casamento.classificar(cert, abas, cfg["casamento"]["limiar_existente"], cfg["casamento"]["limiar_ambiguo"])
            base_info = {"banca": N.BANCAS[chave], "certame": cert.titulo, "órgão": cert.orgao, "UF": cert.uf, "URL": cert.url}
            if res.decisao == "JA_NA_PLANILHA":
                rel[chave]["já na planilha"] += 1
                c0 = res.candidatos[0]
                ja.append({**base_info, "aba": c0.aba, "linha": c0.linha, "CÓD_INTERNO": c0.cod_interno,
                           "CLIENTE": c0.cliente, "situação": c0.situacao, "score": c0.score})
                continue
            if res.decisao == "AMBIGUO":
                rel[chave]["pendente casamento"] += 1
                pendentes.append({**base_info, **{f"cand{i+1}": f"{c.aba} L{c.linha} {c.cod_interno} {c.cliente} ({c.score})"
                                                  for i, c in enumerate(res.candidatos)}})
                continue
            try:
                cert.documentos = ad.listar_documentos(cert)
                for d in cert.documentos:
                    ad.baixar(d)
                if all(vistos.get(d.url) == d.sha256 for d in cert.documentos) and not mudou:
                    rel[chave]["sem documento novo"] += 1
                    continue
                if hasattr(ad, "extrair"):
                    ad.extrair(cert)
                else:
                    extrair_generico(cert)
                linhas = montagem.linhas(cert, ano, cfg["escopo"]["situacao_demanda"])
            except Bloqueado as e:
                falhas.append({"banca": N.BANCAS[chave], "url": cert.url, "motivo": f"BLOQUEADO: {e}"})
                continue
            except montagem.CertameIncompleto as e:
                pendentes.append({**base_info, "motivo": str(e)})
                rel[chave]["incompleto"] += 1
                continue
            novas.extend(linhas)
            rel[chave]["certames EXTERNO"] += 1
            rel[chave]["linhas novas"] += len(linhas)
            for d in cert.documentos:
                vistos[d.url] = d.sha256
    acesso.fechar()
    falhas += [asdict(b) for b in acesso.bloqueios]

    status = Counter(ev.status for ln in novas for _, ev in ln.celulas.values() if ev)
    arquivos = ()
    if not a.dry_run and novas:
        arquivos = planilha.gravar(entrada, cfg["planilha"]["aba"], novas, log,
                                   {"PENDENTES_CASAMENTO": pendentes, "JA_NA_PLANILHA": ja, "FALHAS_ACESSO": falhas},
                                   BASE / cfg["saida_dir"], hoje)
        vistos_p.write_text(json.dumps(vistos, indent=1))

    r = [f"# Execução {hoje:%d/%m/%Y}", f"Entrada: {entrada.name}" + (" (mudou desde a última execução)" if mudou else ""), ""]
    r.append("## Certames 2026 por banca")
    for k, c in rel.items():
        r.append(f"- {N.BANCAS[k]}: " + ", ".join(f"{n} {v}" for n, v in c.items()))
    r += ["", f"## Células preenchidas por status: {dict(status) or '—'}", "",
          f"## Pendências de casamento/extração: {len(pendentes)}"]
    r += [f"- {p['banca']} · {p['órgão']} · {p.get('motivo') or p.get('cand1')}" for p in pendentes]
    r += ["", f"## Sites bloqueados ou com falha: {len(falhas)}"]
    r += [f"- {f['banca']} · {f['url']} · {f['motivo']}" for f in falhas]
    if avisos:
        r += ["", "## Avisos de preservação"] + [f"- {x}" for x in avisos]
    if arquivos:
        r += ["", "## Arquivos"] + [f"- {p}" for p in arquivos]
    texto = "\n".join(r)
    (BASE / cfg["saida_dir"]).mkdir(exist_ok=True)
    (BASE / cfg["saida_dir"] / f"RELATORIO_{hoje:%Y-%m-%d}.md").write_text(texto)
    print(texto)


if __name__ == "__main__":
    main()
