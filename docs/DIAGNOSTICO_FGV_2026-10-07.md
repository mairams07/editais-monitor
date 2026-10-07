# Diagnóstico de acesso — 07/10/2026 10:46

| Banca | Veredito |
|---|---|
| Cebraspe (controle — abre na nuvem) | ABRE (navegador) |
| IBFC (controle — abre na nuvem) | ABRE (navegador) |
| Cesgranrio | ABRE (navegador) |
| Vunesp | BLOQUEADO |
| Instituto AOCP | ABRE (HTTP simples) |
| IDECAN | PARCIAL — bloqueia depois da 1ª página |

## Cebraspe (controle — abre na nuvem)

HTTP simples:
- https://apis.cebraspe.org.br/cebraspe/eventos/tipo/concursos/ → 200 | robots: sem robots.txt legível | sinais: —

Navegador:
- https://apis.cebraspe.org.br/cebraspe/eventos/tipo/concursos/ → 200 | título:  | sinais: — | links de documento: 0

## IBFC (controle — abre na nuvem)

HTTP simples:
- https://concursos.ibfc.org.br/index/abertos/ → 200 | robots: permite | sinais: —

Navegador:
- https://concursos.ibfc.org.br/index/abertos/ → 200 | título: Instituto Brasileiro de Formação e Capacitação | sinais: — | links de documento: 0

## Cesgranrio

HTTP simples:
- https://www.cesgranrio.org.br/ → 200 | robots: sem robots.txt legível | sinais: —
- https://www.cesgranrio.org.br/concursos/ → 200 | robots: sem robots.txt legível | sinais: —

Navegador:
- https://www.cesgranrio.org.br/ → 200 | título: Cesgranrio – Fundação Cesgranrio | sinais: — | links de documento: 2
- https://www.cesgranrio.org.br/concursos/ → 200 | título: CONCURSOS – Cesgranrio | sinais: — | links de documento: 2

## Vunesp

HTTP simples:
- https://www.vunesp.com.br/ → 403 | robots: permite | sinais: Akamai (Access Denied)
- https://www.vunesp.com.br/busca/concurso/em%20andamento → 403 | robots: permite | sinais: Akamai (Access Denied)
- https://www.vunesp.com.br/PMES2601 → 403 | robots: permite | sinais: Akamai (Access Denied)
- https://documento.vunesp.com.br/projeto/PMES2601/documento/ → não acessado (robots.txt) | robots: PROÍBE | sinais: —

Navegador:
- https://www.vunesp.com.br/ → 403 | título: Access Denied | sinais: Akamai (Access Denied) | links de documento: 0
- https://www.vunesp.com.br/busca/concurso/em%20andamento → 403 | título: Access Denied | sinais: Akamai (Access Denied) | links de documento: 0
- https://www.vunesp.com.br/PMES2601 → 403 | título: Access Denied | sinais: Akamai (Access Denied) | links de documento: 0

## Instituto AOCP

HTTP simples:
- https://www.institutoaocp.org.br/concursos/status/em-andamento → 200 | robots: sem robots.txt legível | sinais: —
- https://www.institutoaocp.org.br/concursos/706 → 200 | robots: sem robots.txt legível | sinais: —
- https://www.institutoaocp.org.br/concursos/696 → 200 | robots: sem robots.txt legível | sinais: —
- https://www.institutoaocp.org.br/concursos/693 → 200 | robots: sem robots.txt legível | sinais: —
- https://link.institutoaocp.org.br/api/concursos/706 → 200 | robots: sem robots.txt legível | sinais: —

Navegador:
- https://www.institutoaocp.org.br/concursos/status/em-andamento → 200 | título: Instituto AOCP - Concursos Públicos | sinais: — | links de documento: 0
- https://www.institutoaocp.org.br/concursos/706 → 403 | título: Just a moment... | sinais: Cloudflare (Just a moment), Cloudflare (verificação), Cloudflare Turnstile/captcha | links de documento: 0
- https://www.institutoaocp.org.br/concursos/696 → 403 | título: Just a moment... | sinais: Cloudflare (Just a moment), Cloudflare (verificação), Cloudflare Turnstile/captcha | links de documento: 0
- https://www.institutoaocp.org.br/concursos/693 → 403 | título: Just a moment... | sinais: Cloudflare (Just a moment), Cloudflare (verificação), Cloudflare Turnstile/captcha | links de documento: 0
- https://link.institutoaocp.org.br/api/concursos/706 → 403 | título: Just a moment... | sinais: Cloudflare (Just a moment), Cloudflare (verificação), Cloudflare Turnstile/captcha | links de documento: 0

## IDECAN

HTTP simples:
- https://idecan.org.br/ → 200 | robots: permite | sinais: —
- https://concurso.idecan.org.br/ → 403 | robots: sem robots.txt legível | sinais: Cloudflare (Just a moment), Cloudflare Turnstile/captcha
- https://concurso.idecan.org.br/Concurso.aspx?ID=284 → 403 | robots: sem robots.txt legível | sinais: Cloudflare (Just a moment), Cloudflare Turnstile/captcha

Navegador:
- https://idecan.org.br/ → 200 | título: IDECAN – Instituto de Desenvolvimento Educacional, Cultural e Assistencial Nacio | sinais: — | links de documento: 0
- https://concurso.idecan.org.br/ → 403 | título: Just a moment... | sinais: Cloudflare (Just a moment), Cloudflare (verificação), Cloudflare Turnstile/captcha | links de documento: 0
- https://concurso.idecan.org.br/Concurso.aspx?ID=284 → 403 | título: Just a moment... | sinais: Cloudflare (Just a moment), Cloudflare (verificação), Cloudflare Turnstile/captcha | links de documento: 0