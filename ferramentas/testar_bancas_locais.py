"""Teste dos adaptadores oficiais de Cesgranrio e Instituto AOCP, a partir da rede da FGV.

Roda só a listagem dos certames de 2026 e a extração dos 2 primeiros de cada banca, sem tocar na planilha.
Grava as respostas brutas (listas e APIs) para o Claude ajustar os adaptadores.

Uso:   python ferramentas/testar_bancas_locais.py
Saída: saida/TESTE_BANCAS_<data-hora>.zip  (enviar ao Claude)
"""
from __future__ import annotations

import json
import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import yaml  # noqa: E402

from bancas.aocp import Aocp  # noqa: E402
from bancas.base import Acesso  # noqa: E402
from bancas.cesgranrio import Cesgranrio  # noqa: E402

agora = datetime.now()
pasta = RAIZ / "saida" / f"TESTE_BANCAS_{agora:%Y-%m-%d_%H%M}"
pasta.mkdir(parents=True, exist_ok=True)
cfg = yaml.safe_load(open(RAIZ / "config.yaml", encoding="utf-8"))
acesso = Acesso(cfg["http"], RAIZ / "estado" / "cache")

# grava as primeiras respostas brutas de cada endereço (para diagnóstico)
brutas: list[dict] = []
_texto, _html = acesso.texto, acesso.html


def _grava(fn):
    def w(url, banca, *a, **k):
        try:
            r = fn(url, banca, *a, **k)
            if len(brutas) < 60:
                n = f"bruto_{len(brutas):02d}.txt"
                (pasta / n).write_text(r[:300000], encoding="utf-8")
                brutas.append({"url": url, "arquivo": n, "bytes": len(r)})
            return r
        except Exception as e:
            brutas.append({"url": url, "erro": f"{e.__class__.__name__}: {e}"})
            raise
    return w


acesso.texto, acesso.html = _grava(_texto), _grava(_html)
resumo = {"executado_em": agora.isoformat(timespec="seconds"), "bancas": {}}
for cls in (Cesgranrio, Aocp):
    ad = cls(acesso)
    print(f"→ {cls.__name__}", flush=True)
    r = {"certames": [], "erro": None}
    try:
        cs = ad.listar_certames(2026)
        r["fonte"] = getattr(ad, "fonte", "?")
        for i, c in enumerate(cs):
            item = {"id": c.id_banca, "titulo": c.titulo, "publicado_em": str(c.publicado_em), "url": c.url,
                    "edital": [d.url for d in c.documentos]}
            if i < 2:
                try:
                    for d in c.documentos:
                        ad.baixar(d)
                    ad.extrair(c)
                    item["orgao"] = c.orgao
                    item["cargos"] = [{"nome": g.nome, "esp": g.especialidade,
                                       **{k: str(v.valor) for k, v in g.campos.items()}} for g in c.cargos][:10]
                    item["campos"] = {k: str(v.valor) for k, v in c.campos_certame.items()}
                except Exception as e:
                    item["erro_extracao"] = f"{e.__class__.__name__}: {e}"
            r["certames"].append(item)
    except Exception:
        r["erro"] = traceback.format_exc()[-2000:]
    r["bloqueios"] = [b.__dict__ for b in acesso.bloqueios if b.banca == ad.chave]
    resumo["bancas"][cls.__name__] = r
    print(f"   fonte: {r.get('fonte')} | certames 2026: {len(r['certames'])} | erro: {'sim' if r['erro'] else 'não'}")
acesso.fechar()

(pasta / "_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
(pasta / "_brutas.json").write_text(json.dumps(brutas, ensure_ascii=False, indent=1), encoding="utf-8")
z = RAIZ / "saida" / f"{pasta.name}.zip"
with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
    for x in pasta.iterdir():
        f.write(x, x.name)
print(f"\nPronto. Envie este arquivo ao Claude:\n{z}")
