# Diagnóstico de acesso — 07/10/2026 13:24

| Banca | Veredito |
|---|---|
| Cebraspe (controle — abre na nuvem) | ABRE (navegador) |
| IBFC (controle — abre na nuvem) | ABRE (navegador) |
| Cesgranrio | BLOQUEADO |
| Vunesp | ABRE (navegador) |
| Instituto AOCP | PARCIAL — bloqueia depois da 1ª página |
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
- https://www.cesgranrio.org.br/ → 403 | robots: sem robots.txt legível | sinais: Serviço indisponível
- https://www.cesgranrio.org.br/concursos/ → 403 | robots: sem robots.txt legível | sinais: Serviço indisponível

Navegador:
- https://www.cesgranrio.org.br/ → 403 | título: Service unavailable | sinais: Serviço indisponível | links de documento: 0
- https://www.cesgranrio.org.br/concursos/ → 403 | título: Service unavailable | sinais: Serviço indisponível | links de documento: 0

## Vunesp

HTTP simples:
- https://www.vunesp.com.br/ → 403 | robots: sem robots.txt legível | sinais: Akamai (Access Denied)
- https://www.vunesp.com.br/busca/concurso/em%20andamento → 403 | robots: sem robots.txt legível | sinais: Akamai (Access Denied)
- https://www.vunesp.com.br/PMES2601 → 403 | robots: sem robots.txt legível | sinais: Akamai (Access Denied)
- https://documento.vunesp.com.br/projeto/PMES2601/documento/ → 403 | robots: sem robots.txt legível | sinais: Akamai (Access Denied)

Navegador:
- https://www.vunesp.com.br/ → 200 | título: Fundação Vunesp | Excelência em Concursos, Vestibulares e Avaliações | sinais: — | links de documento: 4
- https://www.vunesp.com.br/busca/concurso/em%20andamento → 200 | título: Fundação Vunesp | Excelência em Concursos, Vestibulares e Avaliações | sinais: — | links de documento: 0
- https://www.vunesp.com.br/PMES2601 → 200 | título: Aluno-Soldado PM do Quadro de Praças (QP) | Polícia Militar/SP | sinais: — | links de documento: 0
- https://documento.vunesp.com.br/projeto/PMES2601/documento/ → 200 | título:  | sinais: — | links de documento: 30

## Instituto AOCP

HTTP simples:
- https://www.institutoaocp.org.br/concursos/status/em-andamento → 403 | robots: sem robots.txt legível | sinais: Cloudflare (Just a moment), Cloudflare Turnstile/captcha
- https://www.institutoaocp.org.br/concursos/706 → 403 | robots: sem robots.txt legível | sinais: Cloudflare (Just a moment), Cloudflare Turnstile/captcha
- https://www.institutoaocp.org.br/concursos/696 → 403 | robots: sem robots.txt legível | sinais: Cloudflare (Just a moment), Cloudflare Turnstile/captcha
- https://www.institutoaocp.org.br/concursos/693 → 403 | robots: sem robots.txt legível | sinais: Cloudflare (Just a moment), Cloudflare Turnstile/captcha
- https://link.institutoaocp.org.br/api/concursos/706 → 403 | robots: sem robots.txt legível | sinais: Cloudflare (Just a moment), Cloudflare Turnstile/captcha

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