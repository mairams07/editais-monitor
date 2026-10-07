"""Coleta páginas de exemplo de Cesgranrio e Instituto AOCP, a partir da rede da FGV.

Esses dois sites abrem no computador da FGV mas não no servidor de nuvem onde o Claude desenvolve. Este script salva
algumas páginas (HTML/JSON) para o Claude ver a estrutura e escrever os adaptadores. Mesmas regras do monitor:
User-Agent identificado, 3–5 s entre acessos, robots.txt respeitado, sem navegador (só HTTP simples).

Uso:   python ferramentas/coletar_amostras.py
Saída: saida/AMOSTRAS_<data-hora>.zip  (enviar ao Claude)
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.robotparser
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

UA = "FGV-IC-editais-monitor/0.1 (+inteligencia competitiva FGV Conhecimento)"
s = requests.Session()
s.headers["User-Agent"] = UA
_ultimo: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
log: list[dict] = []


def esperar(url):
    d = urlparse(url).netloc
    alvo = _ultimo.get(d, 0) + random.uniform(3, 5)
    if time.monotonic() < alvo:
        time.sleep(alvo - time.monotonic())
    _ultimo[d] = time.monotonic()


def permitido(url) -> bool:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = s.get(base + "/robots.txt", timeout=30)
            ok = r.status_code == 200 and "html" not in r.headers.get("content-type", "").lower()
            rp.parse(r.text.splitlines()) if ok else None
            _robots[base] = rp if ok else None
        except requests.RequestException:
            _robots[base] = None
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(UA, url)


def baixar(url, pasta: Path, nome: str):
    if not permitido(url):
        log.append({"url": url, "status": "robots.txt proíbe — não acessado"})
        return None
    esperar(url)
    try:
        r = s.get(url, timeout=40)
    except requests.RequestException as e:
        log.append({"url": url, "status": f"erro {e.__class__.__name__}"})
        return None
    ext = "json" if "json" in r.headers.get("content-type", "") else ("pdf" if r.content[:4] == b"%PDF" else "html")
    if ext != "pdf":                      # PDFs não são salvos (só registrados)
        (pasta / f"{nome}.{ext}").write_bytes(r.content)
    log.append({"url": url, "status": r.status_code, "bytes": len(r.content), "tipo": ext, "arquivo": f"{nome}.{ext}"})
    return r


def links(html: str, base: str, padrao: str) -> list[str]:
    out = []
    for h in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        u = urljoin(base, h)
        if re.search(padrao, u, re.I) and u not in out:
            out.append(u)
    return out


def main():
    raiz = Path(__file__).resolve().parents[1]
    agora = datetime.now()
    pasta = raiz / "saida" / f"AMOSTRAS_{agora:%Y-%m-%d_%H%M}"
    pasta.mkdir(parents=True, exist_ok=True)

    # ---------------- Cesgranrio: home, lista de concursos e até 3 páginas de concurso
    print("→ Cesgranrio", flush=True)
    r = baixar("https://www.cesgranrio.org.br/", pasta, "cesgranrio_home")
    r2 = baixar("https://www.cesgranrio.org.br/concursos/", pasta, "cesgranrio_concursos")
    candidatos = []
    for resp in (r2, r):
        if resp is not None and resp.status_code == 200:
            candidatos += links(resp.text, resp.url, r"cesgranrio\.org\.br/.*(concurso|edital|processo)")
    candidatos = [u for u in dict.fromkeys(candidatos) if not u.rstrip("/").endswith("/concursos")][:3]
    for i, u in enumerate(candidatos, 1):
        resp = baixar(u, pasta, f"cesgranrio_certame_{i}")
        if resp is not None and resp.status_code == 200:
            pdfs = links(resp.text, resp.url, r"\.pdf($|\?)")
            log.append({"url": u, "pdfs_listados": pdfs[:15]})

    # ---------------- Instituto AOCP: listas por situação, 3 certames e a API interna
    print("→ Instituto AOCP", flush=True)
    ids = []
    for st in ("novos", "inscricoes-abertas", "em-andamento", "finalizados"):
        resp = baixar(f"https://www.institutoaocp.org.br/concursos/status/{st}", pasta, f"aocp_lista_{st}")
        if resp is not None and resp.status_code == 200:
            ids += re.findall(r"/concursos/(\d{2,5})\b", resp.text)
    ids = list(dict.fromkeys(ids))[:3] or ["706"]
    for i in ids:
        baixar(f"https://www.institutoaocp.org.br/concursos/{i}", pasta, f"aocp_certame_{i}")
        baixar(f"https://link.institutoaocp.org.br/api/concursos/{i}", pasta, f"aocp_api_{i}")

    (pasta / "_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    zip_path = raiz / "saida" / f"{pasta.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in pasta.iterdir():
            z.write(f, f.name)
    print(f"\nPronto. Envie este arquivo ao Claude:\n{zip_path}")


if __name__ == "__main__":
    main()
