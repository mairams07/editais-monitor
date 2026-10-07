# Diagnóstico de acesso no computador da FGV

Testa, a partir da rede da FGV, se os sites oficiais de Cesgranrio, Vunesp, Instituto AOCP e IDECAN abrem para a
ferramenta. Cebraspe e IBFC entram como controle. A FCC fica de fora (robots.txt proíbe leitura automatizada).
Nada é contornado: User-Agent identificado, 3–5 s entre acessos, robots.txt respeitado, sem interação com captcha.
Duração: cerca de 5 minutos.

## Passo a passo
1. **Python 3.10 ou mais novo.** No Prompt de Comando, digite `python --version`.
   Se não existir, instale pelo site python.org (marque "Add Python to PATH") ou peça à TI.
2. **Baixe o código:** em https://github.com/mairams07/editais-monitor → botão verde **Code** → **Download ZIP**,
   e descompacte numa pasta **fora do OneDrive** (ex.: `C:\editais-monitor`).
3. **Dê dois cliques em `ferramentas\diagnostico.bat`.** Ele instala as dependências (requests, Playwright e o
   navegador Chromium, ~150 MB) e roda o teste.
4. **Envie o relatório:** o arquivo `saida\DIAGNOSTICO_ACESSO_<data>.md` (pode anexar na conversa com o Claude).

## Se algo falhar
- `python` não reconhecido → Python não instalado ou fora do PATH (passo 1).
- Erro ao baixar o Chromium (rede corporativa bloqueia) → o teste roda só por HTTP simples; envie o relatório assim mesmo.
- Proxy corporativo → defina antes no Prompt: `set HTTPS_PROXY=http://<proxy-da-FGV>:<porta>`.
