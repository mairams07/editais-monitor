"""Base dos adaptadores: acesso educado (UA identificado, 2–5 s por domínio, robots.txt) e registro de bloqueio.

Regras: não contornar login, captcha nem bloqueio. Se o HTTP simples for recusado, tenta uma navegação real
(Playwright, uma página por vez). Se ainda assim falhar, registra BLOQUEADO e segue.
"""
from __future__ import annotations

import hashlib
import random
import time
import urllib.robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from modelos import Certame, Documento


@dataclass
class Bloqueio:
    banca: str
    url: str
    motivo: str
    em: str


class Bloqueado(Exception):
    pass


class Acesso:
    def __init__(self, cfg_http: dict, cache_dir: Path):
        self.cfg = cfg_http
        self.s = requests.Session()
        self.s.headers["User-Agent"] = cfg_http["user_agent"]
        self.ultimo: dict[str, float] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        self.bloqueios: list[Bloqueio] = []
        self._pw = None

    # ---------------------------------------------------------------- cortesia
    def _esperar(self, dominio: str):
        alvo = self.ultimo.get(dominio, 0) + random.uniform(self.cfg["intervalo_min_s"], self.cfg["intervalo_max_s"])
        agora = time.monotonic()
        if agora < alvo:
            time.sleep(alvo - agora)
        self.ultimo[dominio] = time.monotonic()

    def permitido(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.s.get(base + "/robots.txt", timeout=self.cfg["timeout_s"])
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp = None
            self.robots[base] = rp
        rp = self.robots[base]
        return True if rp is None else rp.can_fetch(self.cfg["user_agent"], url)

    # ---------------------------------------------------------------- acesso
    def html(self, url: str, banca: str, dinamico: bool = False) -> str:
        """HTML da página. dinamico=True vai direto ao navegador (conteúdo carregado por JS)."""
        if not dinamico:
            try:
                return self._get(url, banca).text
            except Bloqueado:
                if not self.cfg.get("usar_playwright_se_bloqueado"):
                    raise
        return self._navegador(url, banca)

    def texto(self, url: str, banca: str) -> str:
        """Corpo bruto (JSON, texto) via HTTP simples."""
        return self._get(url, banca).text

    def baixar(self, doc: Documento, banca: str) -> Documento:
        r = self._get(doc.url, banca)
        dados = r.content
        doc.sha256 = hashlib.sha256(dados).hexdigest()
        destino = self.cache / banca / f"{doc.sha256[:16]}.pdf"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)
        doc.caminho_local = str(destino)
        return doc

    def _get(self, url: str, banca: str) -> requests.Response:
        if not self.permitido(url):
            self._bloq(banca, url, "robots.txt não permite leitura automatizada")
        self._esperar(urlparse(url).netloc)
        try:
            r = self.s.get(url, timeout=self.cfg["timeout_s"])
        except requests.RequestException as e:
            self._bloq(banca, url, f"falha de conexão: {e.__class__.__name__}")
        if r.status_code in (401, 403, 429) or r.status_code >= 500:
            self._bloq(banca, url, f"HTTP {r.status_code}")
        r.raise_for_status()
        return r

    def _navegador(self, url: str, banca: str) -> str:
        from playwright.sync_api import sync_playwright, Error as PWError
        self._esperar(urlparse(url).netloc)
        try:
            if self._pw is None:
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch(executable_path=self.cfg.get("chromium") or None)
                self._ctx = self._browser.new_context(user_agent=self.cfg["user_agent"])
            pg = self._ctx.new_page()
            try:
                resp = pg.goto(url, wait_until="networkidle", timeout=self.cfg["timeout_s"] * 1000)
                if resp is None or resp.status in (401, 403, 429):
                    self._bloq(banca, url, f"navegador: HTTP {resp.status if resp else '—'}")
                if pg.locator("iframe[src*='captcha'], .g-recaptcha, #cf-challenge-running").count():
                    self._bloq(banca, url, "captcha/desafio anti-robô — não contornado")
                return pg.content()
            finally:
                pg.close()
        except PWError as e:
            self._bloq(banca, url, f"navegador: {str(e).splitlines()[0][:120]}")

    def _bloq(self, banca: str, url: str, motivo: str):
        self.bloqueios.append(Bloqueio(banca, url, motivo, datetime.now().isoformat(timespec="seconds")))
        raise Bloqueado(motivo)

    def fechar(self):
        if self._pw:
            self._browser.close()
            self._pw.stop()


class Adaptador(ABC):
    chave: str          # 'cebraspe', 'aocp', ...
    inicio: str         # URL da lista de certames

    def __init__(self, acesso: Acesso):
        self.acesso = acesso

    @abstractmethod
    def listar_certames(self, ano: int) -> list[Certame]:
        """Certames cujo edital de abertura foi publicado em `ano` (com url, título e data de publicação)."""

    @abstractmethod
    def listar_documentos(self, certame: Certame) -> list[Documento]:
        """Edital, retificações e relações de inscritos, em ordem cronológica."""

    def baixar(self, doc: Documento) -> Documento:
        return self.acesso.baixar(doc, self.chave)
