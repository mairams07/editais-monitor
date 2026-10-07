"""Diagnóstico de acesso aos sites das bancas, para rodar no computador da FGV.

Objetivo: saber se, a partir da rede da FGV (e não de um servidor de nuvem), os sites oficiais abrem sem bloqueio.
Nada é contornado: mesmo User-Agent identificado, 3–5 s entre acessos, robots.txt respeitado, nenhuma interação com
captcha. A FCC fica de fora de propósito (robots.txt proíbe a leitura automatizada de /concursos/ e dos PDFs).

Uso:
    python ferramentas/diagnostico_acesso.py
Saída:
    saida/DIAGNOSTICO_ACESSO_<data-hora>.md  (relatório para enviar ao Claude)
    saida/DIAGNOSTICO_ACESSO_<data-hora>.json
"""
from __future__ import annotations

import json
import random
import sys
import time
import urllib.robotparser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

UA = "FGV-IC-editais-monitor/0.1 (+inteligencia competitiva FGV Conhecimento)"
UA_NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36 FGV-IC-editais-monitor/0.1")

# Para cada banca: páginas na ordem em que a ferramenta as visitaria. Testar várias páginas seguidas mostra se o
# bloqueio aparece só depois da 1ª (caso do Instituto AOCP no teste em nuvem).
TESTES = {
    "Cebraspe (controle — abre na nuvem)": [
        "https://apis.cebraspe.org.br/cebraspe/eventos/tipo/concursos/",
    ],
    "IBFC (controle — abre na nuvem)": [
        "https://concursos.ibfc.org.br/index/abertos/",
    ],
    "Cesgranrio": [
        "https://www.cesgranrio.org.br/",
        "https://www.cesgranrio.org.br/concursos/",
    ],
    "Vunesp": [
        "https://www.vunesp.com.br/",
        "https://www.vunesp.com.br/busca/concurso/em%20andamento",
        "https://www.vunesp.com.br/PMES2601",
        "https://documento.vunesp.com.br/projeto/PMES2601/documento/",
    ],
    "Instituto AOCP": [
        "https://www.institutoaocp.org.br/concursos/status/em-andamento",
        "https://www.institutoaocp.org.br/concursos/706",
        "https://www.institutoaocp.org.br/concursos/696",
        "https://www.institutoaocp.org.br/concursos/693",
        "https://link.institutoaocp.org.br/api/concursos/706",
    ],
    "IDECAN": [
        "https://idecan.org.br/",
        "https://concurso.idecan.org.br/",
        "https://concurso.idecan.org.br/Concurso.aspx?ID=284",
    ],
}

SINAIS_BLOQUEIO = [
    ("Cloudflare (Just a moment)", "just a moment"),
    ("Cloudflare (verificação)", "security verification"),
    ("Cloudflare Turnstile/captcha", "challenges.cloudflare.com"),
    ("Akamai (Access Denied)", "access denied"),
    ("reCAPTCHA", "g-recaptcha"),
    ("Serviço indisponível", "service unavailable"),
]

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_ultimo: dict[str, float] = {}


def esperar(url: str):
    d = urlparse(url).netloc
    alvo = _ultimo.get(d, 0) + random.uniform(3, 5)
    if time.monotonic() < alvo:
        time.sleep(alvo - time.monotonic())
    _ultimo[d] = time.monotonic()


def robots_permite(s: requests.Session, url: str) -> str:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = s.get(base + "/robots.txt", timeout=30)
            if r.status_code == 200 and "html" not in r.headers.get("content-type", "").lower():
                rp.parse(r.text.splitlines())
            else:
                rp = None
        except requests.RequestException:
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    if rp is None:
        return "sem robots.txt legível"
    return "permite" if rp.can_fetch(UA, url) else "PROÍBE"


def sinais(texto: str) -> list[str]:
    t = texto.lower()
    return [nome for nome, chave in SINAIS_BLOQUEIO if chave in t]


def teste_http(s: requests.Session, url: str) -> dict:
    esperar(url)
    try:
        r = s.get(url, timeout=40)
        return {"status": r.status_code, "bytes": len(r.content), "sinais": sinais(r.text[:20000])}
    except requests.RequestException as e:
        return {"status": None, "erro": e.__class__.__name__}


def teste_navegador(urls: list[str]) -> list[dict] | str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Playwright não instalado — teste de navegador pulado"
    out = []
    try:
        with sync_playwright() as p:
            import os
            exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
            b = p.chromium.launch(executable_path=exe)
            ctx = b.new_context(user_agent=UA_NAVEGADOR)
            pg = ctx.new_page()
            for url in urls:
                esperar(url)
                try:
                    r = pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                    pg.wait_for_timeout(8000)          # tempo para verificação passiva terminar sozinha (sem clicar)
                    html = pg.content()
                    out.append({"url": url, "status": r.status if r else None, "titulo": pg.title()[:80],
                                "sinais": sinais(html[:50000]),
                                "links_pdf": html.lower().count(".pdf") + html.count("documento/stream")})
                except Exception as e:
                    out.append({"url": url, "erro": str(e).splitlines()[0][:120]})
            b.close()
    except Exception as e:
        return f"Navegador não abriu: {str(e).splitlines()[0][:160]} (rode: python -m playwright install chromium)"
    return out


def veredito(http: list[dict], nav) -> str:
    def ok(x):
        return x.get("status") == 200 and not x.get("sinais")
    if isinstance(nav, list) and nav and all(ok(x) for x in nav):
        return "ABRE (navegador)"
    if all(ok(x) for x in http):
        return "ABRE (HTTP simples)"
    if isinstance(nav, list) and nav and ok(nav[0]) and not all(ok(x) for x in nav):
        return "PARCIAL — bloqueia depois da 1ª página"
    return "BLOQUEADO"


def main():
    raiz = Path(__file__).resolve().parents[1]
    saida = raiz / "saida"
    saida.mkdir(exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    agora = datetime.now()
    resultado = {"executado_em": agora.isoformat(timespec="seconds"), "python": sys.version.split()[0], "bancas": {}}
    for banca, urls in TESTES.items():
        print(f"→ {banca}", flush=True)
        http = []
        for u in urls:
            r = {"url": u, "robots": robots_permite(s, u)}
            if r["robots"] == "PROÍBE":
                r["status"] = "não acessado (robots.txt)"
            else:
                r.update(teste_http(s, u))
            http.append(r)
        nav = teste_navegador([h["url"] for h in http if h["robots"] != "PROÍBE"])
        resultado["bancas"][banca] = {"http": http, "navegador": nav, "veredito": veredito(http, nav)}

    nome = f"DIAGNOSTICO_ACESSO_{agora:%Y-%m-%d_%H%M}"
    (saida / f"{nome}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# Diagnóstico de acesso — {agora:%d/%m/%Y %H:%M}", "", "| Banca | Veredito |", "|---|---|"]
    md += [f"| {b} | {v['veredito']} |" for b, v in resultado["bancas"].items()]
    for b, v in resultado["bancas"].items():
        md += ["", f"## {b}", "", "HTTP simples:"]
        md += [f"- {h['url']} → {h.get('status')} | robots: {h['robots']} | sinais: {', '.join(h.get('sinais', [])) or '—'}"
               for h in v["http"]]
        md += ["", "Navegador:"]
        if isinstance(v["navegador"], str):
            md.append(f"- {v['navegador']}")
        else:
            md += [f"- {n['url']} → {n.get('status', n.get('erro'))} | título: {n.get('titulo', '')} | "
                   f"sinais: {', '.join(n.get('sinais', [])) or '—'} | links de documento: {n.get('links_pdf', '—')}"
                   for n in v["navegador"]]
    (saida / f"{nome}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:4 + len(resultado['bancas'])]))
    print(f"\nRelatório: {saida / (nome + '.md')}")


if __name__ == "__main__":
    main()
