"""Execução: lista certames 2026 das 7 bancas, descarta os que já estão na planilha e inclui os demais como EXTERNO.

Uso:
  python run.py                 # execução completa
  python run.py --banca aocp    # só uma banca
  python run.py --dry-run       # não grava planilha; só relatório
"""
from __future__ import annotations

import argparse
import re
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
from bancas import pncp
from bancas.base import Acesso, Bloqueado
from extracao import campos, llm, pdf
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


def exportar_pacote(pasta: Path, cert: Certame, chave: str, manifesto: list) -> None:
    """Páginas selecionadas do edital em PASTA/<n>.txt + entrada no manifesto (para a leitura na sessão)."""
    ed = next((d for d in cert.documentos if d.tipo == "edital" and d.caminho_local), None)
    if ed is None:
        return
    pasta.mkdir(parents=True, exist_ok=True)
    n = len(manifesto) + 1
    pags = llm.selecionar_paginas(campos.recortar_edital(pdf.ler(ed.caminho_local)))
    (pasta / f"{n:03d}.txt").write_text(llm.texto_paginado(pags), encoding="utf-8")
    manifesto.append({"n": n, "banca": chave, "id": cert.id_banca, "url": cert.url, "titulo": cert.titulo,
                      "orgao_regras": cert.orgao, "uf": cert.uf, "tipo": cert.tipo,
                      "publicado_em": str(cert.publicado_em or ""),
                      "documento": {"titulo": ed.titulo, "url": ed.url, "caminho": ed.caminho_local,
                                    "copia_terceiro": ed.copia_terceiro, "sha256": ed.sha256}})


def aplicar_leituras(a, pasta: Path) -> None:
    """Etapa 2 da leitura na sessão: aplica PASTA/<n>.json (conferência no PDF), deduplica de novo com o órgão lido e
    grava a saída (aba A_CONFERIR, RADAR_PNCP, DESCARTES_IA, pendências)."""
    from datetime import date as _date
    cfg = yaml.safe_load(open(a.config))
    man = json.loads((pasta / "manifesto.json").read_text())
    entrada = Path(man["entrada"])
    abas = [planilha.ler_aba(entrada, n) for n in cfg["planilha"]["abas_deduplicacao"]]
    novas, log, descartes, pendentes, ja = [], [], [], list(man["pendentes"]), list(man["ja"])
    externos, vistos_cargos = [], set()
    for m in man["certames"]:
        arq = pasta / f"{m['n']:03d}.json"
        info = {"banca": N.BANCAS[m["banca"]], "certame": m["titulo"], "órgão": m["orgao_regras"], "UF": m["uf"], "URL": m["url"]}
        if not arq.exists():
            pendentes.append({**info, "motivo": "leitura não feita"})
            continue
        d = m["documento"]
        doc = __import__("modelos").Documento(d["titulo"], d["url"], "edital", copia_terceiro=d["copia_terceiro"])
        doc.caminho_local, doc.sha256 = d["caminho"], d["sha256"]
        cert = Certame(m["banca"], m["id"], m["url"], titulo=m["titulo"], orgao=m["orgao_regras"] or "", uf=m["uf"] or "",
                       tipo=m["tipo"] or "", documentos=[doc])
        if m.get("publicado_em"):
            cert.publicado_em = _date.fromisoformat(m["publicado_em"])
        pags = llm.selecionar_paginas(campos.recortar_edital(pdf.ler(d["caminho"])))
        nome_doc = d["titulo"] + (" (cópia do PDF oficial)" if d["copia_terceiro"] else "")
        bruto = json.loads(arq.read_text(encoding="utf-8"))
        descartes += [{"banca": info["banca"], "certame": m["titulo"], **x} for x in llm.aplicar(cert, bruto, pags, nome_doc, d["url"])]
        if not bruto.get("eh_edital_de_abertura", True):
            pendentes.append({**info, "motivo": "a leitura indicou que o documento não é edital de abertura"})
            continue
        res = casamento.classificar(cert, abas, cfg["casamento"]["limiar_existente"], cfg["casamento"]["limiar_ambiguo"])
        info["órgão"] = cert.orgao
        if res.decisao == "JA_NA_PLANILHA":
            c0 = res.candidatos[0]
            ja.append({**info, "aba": c0.aba, "linha": c0.linha, "CÓD_INTERNO": c0.cod_interno, "CLIENTE": c0.cliente,
                       "BANCA na planilha": c0.banca, "situação": c0.situacao, "score": c0.score})
            continue
        if res.decisao == "AMBIGUO":
            pendentes.append({**info, "motivo": "casamento ambíguo",
                              **{f"cand{i+1}": f"{c.aba} L{c.linha} {c.cod_interno} {c.cliente} ({c.score})"
                                 for i, c in enumerate(res.candidatos)}})
            continue
        k = (N.texto(cert.orgao), frozenset(N.texto(f"{g.nome} {g.especialidade}") for g in cert.cargos))
        if k in vistos_cargos:
            continue
        vistos_cargos.add(k)
        try:
            linhas = montagem.linhas(cert, man["ano"], cfg["escopo"]["situacao_demanda"])
        except montagem.CertameIncompleto as e:
            pendentes.append({**info, "motivo": str(e)})
            continue
        novas.extend(linhas)
        externos.append((cert.orgao, cert.uf or "", linhas))
    # valor global do contrato PNCP para os certames lidos
    radar = man.get("radar") or []
    estado = BASE / cfg["estado_dir"] / "radar_pncp.json"
    contratos = json.loads(estado.read_text()) if estado.exists() else {}
    for c in contratos.values():
        for cli, uf, linhas in externos:
            if pncp.mesmo_orgao(c, cli, uf):
                c["situacao"], c["certame"] = "edital localizado", cli
                vg = c.get("valor_global")
                if vg and float(vg) > 1:
                    ev = Evidencia(float(vg), "CONFIRMADO", f"Contrato PNCP {c['id']}", None,
                                   f"valor global do contrato com {c['fornecedor']}, assinado em {c['data_assinatura']}", c["link"])
                    for ln in linhas:
                        ln.celulas["VALOR_GLOBAL"] = (float(vg), ev)
                break
    if contratos:
        pncp.salvar_radar(BASE / cfg["estado_dir"], contratos)
        radar = [{k: c.get(k) for k in ("situacao", "banca", "orgao", "unidade", "uf", "municipio", "objeto", "valor_global",
                                        "data_assinatura", "fundamento", "fornecedor", "link", "visto_em", "certame")}
                 for c in contratos.values()]
    arquivos = planilha.gravar(entrada, cfg["planilha"]["aba"], novas, log,
                               {"RADAR_PNCP": radar, "DESCARTES_IA": descartes, "PENDENTES_CASAMENTO": pendentes,
                                "JA_NA_PLANILHA": ja, "FALHAS_ACESSO": man["falhas"]},
                               BASE / cfg["saida_dir"], date.today(), modo=cfg.get("saida", {}).get("modo", "revisao"))
    print(f"{len(novas)} linha(s) em A_CONFERIR de {len(externos)} certame(s); {len(descartes)} valor(es) descartado(s) "
          f"pela conferência; {len(pendentes)} pendência(s).")
    print("\n".join(str(p) for p in arquivos))


def main(argv=None):
    from versao import VERSAO
    print(f"Versão do código: {VERSAO}  (pasta: {BASE})", flush=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--banca", action="append", help="limita a execução a esta(s) banca(s)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", default=str(BASE / "config.yaml"))
    ap.add_argument("--exportar-leituras", metavar="PASTA",
                    help="leitura na sessão (sem chave da API): grava as páginas selecionadas de cada candidato a EXTERNO "
                         "em PASTA e para; a leitura volta em PASTA/<n>.json e é aplicada com --aplicar-leituras")
    ap.add_argument("--aplicar-leituras", metavar="PASTA", help="aplica as leituras de PASTA (com conferência) e grava a saída")
    a = ap.parse_args(argv)
    if a.aplicar_leituras:
        return aplicar_leituras(a, Path(a.aplicar_leituras))
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
    ja_vistos_pdf: set = set()
    ja_vistos_cargos: set = set()
    descartes_ia: list[dict] = []
    manifesto: list[dict] = []
    usar_ia = cfg.get("extracao", {}).get("ia", True) and llm.disponivel()
    print("Leitura dos editais: " + ("IA (Claude) com conferência no PDF" if usar_ia else
                                     "regras (sem credencial da API da Anthropic)"), flush=True)
    certames_externos: list[tuple[str, str, list]] = []      # (cliente, uf, linhas) — para o radar PNCP
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
            base_info = lambda: {"banca": N.BANCAS[chave], "certame": cert.titulo, "órgão": cert.orgao, "UF": cert.uf, "URL": cert.url}
            # 1) documentos e extração ANTES da deduplicação: em várias bancas o órgão só aparece no edital
            try:
                cert.documentos = ad.listar_documentos(cert)
                for d in cert.documentos:
                    ad.baixar(d)
                if not cert.documentos:
                    pendentes.append({**base_info(), "motivo": "EDITAL NÃO LOCALIZADO"})
                    rel[chave]["edital não localizado"] += 1
                    continue
                if all(vistos.get(d.url) == d.sha256 for d in cert.documentos) and not mudou:
                    rel[chave]["sem documento novo"] += 1
                    continue
                feito = False
                if usar_ia:
                    # leitura do edital pela IA; cada valor conferido no PDF (extracao/llm.py). Falha → regras.
                    try:
                        ed = next(d for d in cert.documentos if d.tipo == "edital" and d.caminho_local)
                        pags = llm.selecionar_paginas(campos.recortar_edital(pdf.ler(ed.caminho_local)))
                        nome_doc = ed.titulo + (" (cópia do PDF oficial)" if ed.copia_terceiro else "")
                        descartes_ia.extend({"banca": N.BANCAS[chave], "certame": cert.titulo, **d}
                                            for d in llm.aplicar(cert, llm.chamar_modelo(pags), pags, nome_doc, ed.url))
                        feito = bool(cert.cargos)
                        rel[chave]["lidos pela IA"] += 1
                    except Exception as e:
                        descartes_ia.append({"banca": N.BANCAS[chave], "certame": cert.titulo, "cargo": "", "campo": "(todos)",
                                             "valor": "", "motivo": f"leitura pela IA falhou ({e.__class__.__name__}); usadas as regras"})
                if not feito:
                    if hasattr(ad, "extrair"):
                        ad.extrair(cert)
                    else:
                        extrair_generico(cert)
            except Bloqueado as e:
                falhas.append({"banca": N.BANCAS[chave], "url": cert.url, "motivo": f"BLOQUEADO: {e}"})
                continue
            except Exception as e:  # PDF corrompido/ilegível: não derruba a execução
                pendentes.append({**base_info(), "motivo": f"falha na leitura do edital: {e.__class__.__name__}: {str(e)[:120]}"})
                rel[chave]["falha de leitura"] += 1
                continue
            # seleção da própria banca (ex.: Jovem Aprendiz do IBFC) não é cliente
            if N.banca(cert.orgao) == chave or re.search(r"INSTITUTO BRASILEIRO DE FORMACAO|FUNDACAO CARLOS CHAGAS|FUNDACAO CESGRANRIO|"
                                                          r"FUNDACAO VUNESP|CEBRASPE|INSTITUTO AOCP|IDECAN", N.texto(cert.orgao)):
                rel[chave]["seleção própria da banca"] += 1
                continue
            if a.exportar_leituras and not cert.orgao:
                exportar_pacote(Path(a.exportar_leituras), cert, chave, manifesto)
                rel[chave]["exportados para leitura (órgão a identificar)"] += 1
                continue
            # 2a) o mesmo edital não entra duas vezes na mesma rodada (ex.: PDF oficial e cópia em site especializado,
            #     ou o mesmo certame listado por duas fontes): mesmo PDF ou mesmo órgão com os mesmos cargos
            k_pdf = {d.sha256 for d in cert.documentos if d.sha256}
            k_cargos = (N.texto(cert.orgao), frozenset(N.texto(f"{g.nome} {g.especialidade}") for g in cert.cargos))
            if (k_pdf & ja_vistos_pdf) or (cert.cargos and k_cargos in ja_vistos_cargos):
                rel[chave]["repetido na rodada"] += 1
                ja.append({**base_info(), "aba": "(esta rodada)", "linha": "", "CÓD_INTERNO": "", "CLIENTE": cert.orgao,
                           "BANCA na planilha": "", "situação": "repetido — mesmo edital já processado nesta rodada", "score": ""})
                continue
            ja_vistos_pdf |= k_pdf
            if cert.cargos:
                ja_vistos_cargos.add(k_cargos)
            # 2b) deduplicação com a planilha: certame cujo órgão já está nas abas 2025/2026 (qualquer situação,
            #     inclusive demandas recebidas pela FGV e EXTERNO já lançados) não é analisado
            res = casamento.classificar(cert, abas, cfg["casamento"]["limiar_existente"], cfg["casamento"]["limiar_ambiguo"])
            if res.decisao == "JA_NA_PLANILHA":
                rel[chave]["já na planilha"] += 1
                c0 = res.candidatos[0]
                ja.append({**base_info(), "aba": c0.aba, "linha": c0.linha, "CÓD_INTERNO": c0.cod_interno,
                           "CLIENTE": c0.cliente, "BANCA na planilha": c0.banca, "situação": c0.situacao, "score": c0.score})
                for d in cert.documentos:
                    vistos[d.url] = d.sha256
                continue
            if res.decisao == "AMBIGUO":
                rel[chave]["pendente casamento"] += 1
                pendentes.append({**base_info(), "motivo": "casamento ambíguo",
                                  **{f"cand{i+1}": f"{c.aba} L{c.linha} {c.cod_interno} {c.cliente} ({c.score})"
                                     for i, c in enumerate(res.candidatos)}})
                continue
            # 3) linhas EXTERNO
            if a.exportar_leituras:
                exportar_pacote(Path(a.exportar_leituras), cert, chave, manifesto)
                rel[chave]["exportados para leitura"] += 1
                continue
            try:
                linhas = montagem.linhas(cert, ano, cfg["escopo"]["situacao_demanda"])
            except montagem.CertameIncompleto as e:
                pendentes.append({**base_info(), "motivo": str(e)})
                rel[chave]["incompleto"] += 1
                continue
            novas.extend(linhas)
            certames_externos.append((cert.orgao, cert.uf or "", linhas))
            rel[chave]["certames EXTERNO"] += 1
            rel[chave]["linhas novas"] += len(linhas)
            for d in cert.documentos:
                vistos[d.url] = d.sha256
    # Radar PNCP: contratos órgão × banca. O edital costuma sair meses depois do contrato, então o contrato fica na
    # lista "aguardando edital" (estado/radar_pncp.json) até um certame do mesmo órgão aparecer numa rodada.
    radar_linhas = []
    if cfg.get("pncp", {}).get("ativo", True):
        novos = []
        for chave in a.banca or cfg["bancas_ativas"]:
            try:
                novos += pncp.buscar(acesso, chave, meses=cfg.get("pncp", {}).get("meses", 18))
            except Exception as e:
                falhas.append({"banca": N.BANCAS[chave], "url": "PNCP", "motivo": f"consulta ao PNCP falhou: {e}"})
        radar = pncp.atualizar_radar(BASE / cfg["estado_dir"], novos)
        for c in radar.values():
            vg = c.get("valor_global")
            for cli, uf, linhas in certames_externos:
                if pncp.mesmo_orgao(c, cli, uf):
                    c["situacao"] = "edital localizado"
                    c["certame"] = cli
                    if vg and float(vg) > 1:
                        ev = Evidencia(float(vg), "CONFIRMADO", f"Contrato PNCP {c['id']}", None,
                                       f"valor global do contrato com {c['fornecedor']}, assinado em {c['data_assinatura']}",
                                       c["link"])
                        for ln in linhas:
                            ln.celulas["VALOR_GLOBAL"] = (float(vg), ev)
                    break
            else:
                if c.get("situacao") == "aguardando edital":
                    res = casamento.classificar(Certame(c["banca"], c["id"], c["link"], orgao=c.get("orgao") or "",
                                                        uf=c.get("uf") or ""), abas, 90, 90)
                    if res.decisao == "JA_NA_PLANILHA":
                        c["situacao"] = f"órgão já na planilha ({res.candidatos[0].aba} L{res.candidatos[0].linha})"
            radar_linhas.append({k: c.get(k) for k in ("situacao", "banca", "orgao", "unidade", "uf", "municipio", "objeto",
                                                        "valor_global", "data_assinatura", "fundamento", "fornecedor",
                                                        "link", "visto_em", "certame")})
        pncp.salvar_radar(BASE / cfg["estado_dir"], radar)
        radar_linhas.sort(key=lambda d: (d["situacao"] != "aguardando edital", d.get("data_assinatura") or ""), reverse=False)
        rel["pncp"]["contratos no radar"] = len(radar_linhas)
        rel["pncp"]["aguardando edital"] = sum(1 for d in radar_linhas if d["situacao"] == "aguardando edital")
    acesso.fechar()
    falhas += [asdict(b) for b in acesso.bloqueios]

    if a.exportar_leituras:
        pasta = Path(a.exportar_leituras)
        (pasta / "manifesto.json").write_text(json.dumps({"entrada": str(entrada), "ano": ano, "certames": manifesto,
                                                          "pendentes": pendentes, "ja": ja, "falhas": falhas,
                                                          "radar": radar_linhas}, ensure_ascii=False, indent=1, default=str))
        print(f"\n{len(manifesto)} edital(is) exportado(s) para leitura em {pasta}")
        return
    status = Counter(ev.status for ln in novas for _, ev in ln.celulas.values() if ev)
    arquivos = ()
    if not a.dry_run and (novas or radar_linhas):
        arquivos = planilha.gravar(entrada, cfg["planilha"]["aba"], novas, log,
                                   {"RADAR_PNCP": radar_linhas, "DESCARTES_IA": descartes_ia,
                                    "PENDENTES_CASAMENTO": pendentes, "JA_NA_PLANILHA": ja, "FALHAS_ACESSO": falhas},
                                   BASE / cfg["saida_dir"], hoje, modo=cfg.get("saida", {}).get("modo", "revisao"))
        vistos_p.write_text(json.dumps(vistos, indent=1))

    r = [f"# Execução {hoje:%d/%m/%Y}", f"Entrada: {entrada.name}" + (" (mudou desde a última execução)" if mudou else ""), ""]
    r.append("## Certames 2026 por banca")
    for k, c in rel.items():
        r.append(f"- {N.BANCAS.get(k, k.upper())}: " + ", ".join(f"{n} {v}" for n, v in c.items()))
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
