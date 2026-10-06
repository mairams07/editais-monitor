# Etapa 0 — acesso aos sites (verificado em 06/10/2026)

UA identificado, 2–5 s entre requisições por domínio, sem contornar login, captcha ou bloqueio.

| Banca | HTTP simples | Navegador real | robots.txt | Lista de certames | Documentos | Situação |
|---|---|---|---|---|---|---|
| Cebraspe | 200 | 200 | libera tudo | API JSON pública `apis.cebraspe.org.br/cebraspe/eventos/tipo/concursos/` (fases Novos/Abertas/Andamento/Encerrados, com `eventoAno`) | `apis.cebraspe.org.br/cebraspe/eventos/{slug}` → `arquivosEdital` com data; PDFs em `cdn.cebraspe.org.br` (200) | **ABRE** |
| Instituto AOCP | 403 (desafio Cloudflare) | 200 (desafio passivo resolvido pelo navegador, sem interação) | — | `/concursos/status/{novos,inscricoes-abertas,em-andamento,resultados-disponiveis,finalizados}` → `/concursos/{id}` | `arquivos-site.institutoaocp.org.br/publicacoes/{uuid}.pdf` (200 via HTTP simples), com data no título | **ABRE via navegador** |
| IBFC | 200 | 200 | bloqueia `/admin`, `/painel`, `/uploads` | `/index/abertos/`, `/index/1/`, `/index/3/` → `/informacoes/{id}/` | `servidor-arquivos.ibfc.org.br/arquivos-publicos/*.pdf` (200); listas em `fs.ibfc.org.br`; publica "Quantitativo de Inscritos" | **ABRE** |
| Vunesp | 403 (Akamai "Access Denied") | 200 | não legível (403) | `/busca/concurso/{proximo,inscricoes abertas,em andamento,encerrados}`; código do certame traz o ano (`PMES2601` = 2026) | página `/{CÓDIGO}` abre; links de documento não aparecem como `<a>` — mecanismo a mapear; `documento.vunesp.com.br` 403 em HTTP simples | **ABRE via navegador; documentos a mapear** |
| FCC | 200 | 200 | **proíbe `/concursos/` e `*.pdf`** | `concursoNovo.html`, `concursoAndamento.html`, `concursoOutraSituacao.html` (permitidas) | páginas do certame e PDFs ficam em caminhos proibidos | **LISTA SIM, DOCUMENTOS BLOQUEADO (robots.txt)** |
| IDECAN | 200 (`idecan.org.br`) | 200 na home; `concurso.idecan.org.br` exige Cloudflare Turnstile | — | home `idecan.org.br` lista `Concurso.aspx?ID=…` com título | `concurso.idecan.org.br` → captcha | **LISTA SIM, DOCUMENTOS BLOQUEADO (captcha)** |
| Cesgranrio | 403 | 403 "Service unavailable" | 403 | — | — | **BLOQUEADO** |
| PNCP | 200 | — | — | API `pncp.gov.br/api/consulta/v1/contratos` responde | — | **ABRE** |

Cebraspe, contagem por `eventoAno` na API: Novos 2 (2026), Inscrições abertas 6 (2026), Em andamento 38 (2026), Encerrados 5 (2026).
