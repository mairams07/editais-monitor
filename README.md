# editais-monitor

Inteligência Competitiva — FGV Conhecimento. Lista os certames de **2026** organizados por Cebraspe, FCC, Cesgranrio,
Vunesp, IDECAN, Instituto AOCP e IBFC e inclui na aba `2026` da `CONCORRENTES_FGV.xlsx`, como
`Situação da Demanda = EXTERNO`, os que **não** chegaram à FGV como demanda.

## Escopo (decidido em 06/10/2026)
- **Entra:** edital de abertura publicado em 2026; concursos, processos seletivos, residências, vestibulares e exames.
- **Fica de fora:** certame cujo órgão já aparece nas abas 2025 ou 2026 (qualquer banca, qualquer situação) — a FGV
  recebeu a demanda. Casos duvidosos vão para `PENDENTES_CASAMENTO`, nunca para a planilha.
- **Uma linha por cargo/especialidade.** `CLIENTE` (nome do órgão como no edital, caixa alta) é obrigatório; sem ele
  o certame não é gravado. `TIPO`, `OBJETO` e `SEGMENTO` preenchidos (SEGMENTO sempre como INDÍCIO);
  `CÓD_INTERNO`, `Cód Proposta` e `Receita Estimada` ficam vazios.
- Linhas já existentes **não são alteradas**.

## Fontes
Site da banca (principal) → site do órgão/Diário Oficial (confirmação) → PNCP (só valor global).
Blogs só como pista; cópia do PDF oficial em CDN de terceiro aceita quando cabeçalho, nº e data batem (registrada no LOG).

## Saída (`saida/`, fora da pasta do OneDrive)
- `CONCORRENTES_FGV_atualizado_{data}.xlsx` — cópia com as linhas novas (verde `C6EFCE` = CONFIRMADO,
  amarelo-claro `FFEB9C` = INDÍCIO) e abas `LOG`, `PENDENTES_CASAMENTO`, `JA_NA_PLANILHA`, `FALHAS_ACESSO`.
- `ALTERACOES_{data}.xlsx` — uma linha por célula incluída, ordenada por aba e linha, para lançar no Excel Online.
- `RELATORIO_{data}.md`.

## Uso
```
pip install -r requirements.txt
python run.py --dry-run            # não grava planilha
python run.py --banca aocp
python -m pytest -rs tests         # núcleo + gabarito (gabarito precisa de rede)
```
Configure `planilha.caminho_sincronizado` em `config.yaml` com o caminho da cópia sincronizada do OneDrive, ou
coloque a cópia em `entrada/`. O original nunca é aberto para escrita.

## Estado
| Parte | Situação |
|---|---|
| Leitura da planilha, normalização, deduplicação, gravação, LOG, ALTERACOES | pronto, testado |
| Extração genérica (taxa, quadro de vagas/vencimento, etapas, cidades) | escrito; validação contra gabarito depende de rede |
| Adaptadores por banca | pendentes da Etapa 0 (rede do ambiente bloqueada em 06/10/2026) |
| Agendamento diário (Windows) | após aprovação do piloto |
