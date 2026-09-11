---
versão: 1.0
lote: feat-0002-teste-ponta-a-ponta
origem: .codeflow/bugs/INDEX.md (cinco relatos em .codeflow/bugs/, commit c3603f7)
criado: 2026-08-17
atualizado: 2026-08-18
placar: 5 corrigido, 0 bloqueado, 0 não-reproduz
verificação: 5 sanados (✓), 0 não sanados (✗), 0 inconclusivos (⚠) — /double-check de 2026-08-18
---

# Lote `feat-0002-teste-ponta-a-ponta`

Cinco defeitos encontrados no teste de ponta a ponta do owner em 2026-08-17,
antes da fase `B.5`. Cada bug tem relato próprio em `.codeflow/bugs/`; este
ledger é o contrato de execução e a entrada do `/double-check`.

## Decisões do owner tomadas na abertura do lote

- **BUG-003** — caminho **(1) renomear na interface**: o rótulo passa a dizer
  "trechos consultados", e FR-8 é corrigido na spec para descrever o que o
  código de fato emite. Descartados o (2) — pedir os índices ao modelo, que
  colide com o BUG-005 — e o (3) — baixar `RETRIEVAL_TOP_K`, que interage com a
  recalibração do BUG-002.
- **BUG-002** — autorizado rodar `make eval` contra a API real (quota de
  embedding, balde separado do de geração), que é o que permite recalibrar o
  limiar com dado medido em vez de palpite.

## Bugs

| id | título | status | repro/teste | fix (arquivo:linha) | decision | verificação |
|----|--------|--------|-------------|---------------------|----------|-------------|
| B1 | Continuação de 4 palavras não condensa → recusa falsa | corrigido | `backend/tests/test_condensation.py::test_fronteira_de_tamanho_condensa_ate_quatro_palavras_e_para_na_quinta` + `::test_formas_contraidas_sao_reconhecidas_como_marcador_anaforico` | `backend/app/core/condensation.py:29` (formas contraídas) e `:68` (limiar 4→5) | 2026-08-17-lote-de-bugs-do-teste-de-ponta-a-ponta.md | ✓ 2026-08-18 |
| B5 | Resposta cita "Trecho N", rótulo que não existe na tela | corrigido | `backend/tests/test_prompt.py::test_prompt_proibe_citar_o_numero_do_trecho_e_manda_citar_so_a_pagina` (instrução presente) + repro manual: perguntar `Quem fundou a empresa?` na interface e conferir que a resposta cita só a página | `backend/app/core/prompt.py:36` | 2026-08-17-lote-de-bugs-do-teste-de-ponta-a-ponta.md | ✓ 2026-08-18 |
| B2 | Limiar 0,625 recusa perguntas legítimas | corrigido | `EVAL_DOCUMENT_ID=ce4e9cd0-fa3a-45e4-852d-5103b73fb736 make eval` (gate NFR-7, exit 0) + `backend/tests/test_eval_metrics.py::TestDataset` | `backend/app/config.py:51` (0,625→0,561), `backend/eval/dataset.json` (+P11–P16, +C03), `.env.example:44` | 2026-08-17-lote-de-bugs-do-teste-de-ponta-a-ponta.md | ✓ 2026-08-18 |
| B3 | Citações exibem os chunks recuperados, não os usados | corrigido | `frontend/src/components/CitationChip.test.tsx` → "diz que o trecho foi consultado, não que ele sustentou a resposta" | `frontend/src/components/CitationChip.tsx:51,61,63`, `frontend/src/components/MessageList.tsx:130`, `.codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md:87,95` (FR-8) e AC-10 | 2026-08-17-lote-de-bugs-do-teste-de-ponta-a-ponta.md | ✓ 2026-08-18 |
| B4 | Mensagem de quota promete "um minuto"; o limite é diário | corrigido | `backend/tests/test_gemini_adapter.py::test_mensagem_de_quota_do_chat_nao_promete_um_minuto` + `frontend/src/lib/errors.test.ts` → "não promete que esperar um minuto resolve o limite de uso" | `backend/app/adapters/gemini.py:67`, `frontend/src/lib/errors.ts:65` | 2026-08-17-lote-de-bugs-do-teste-de-ponta-a-ponta.md | ✓ 2026-08-18 |

## Fila e escopo esperado (Passo 2)

A ordem agrupa por área para reduzir troca de contexto: os dois da `A.2` (núcleo
puro) primeiro, depois a calibração da `A.5`, e por fim os dois de texto de
interface.

| ordem | id | fase dona | escopo esperado |
|---|----|-----------|-----------------|
| 1 | B1 | A.2 | `backend/app/core/condensation.py`, `backend/tests/test_condensation.py` |
| 2 | B5 | A.2 | `backend/app/core/prompt.py`, `backend/tests/test_prompt.py` |
| 3 | B2 | A.5 | `backend/eval/dataset.json`, `backend/app/config.py`, `.env.example`, `backend/eval/README.md`, `backend/tests/test_eval_metrics.py`, `backend/tests/test_config.py` |
| 4 | B3 | A.4 / B.3 | `frontend/src/components/CitationChip.tsx`, `frontend/src/components/MessageList.tsx`, testes do frontend, `.codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md` (FR-8) |
| 5 | B4 | B.4 / A.4 | `backend/app/adapters/gemini.py`, `frontend/src/lib/errors.ts`, testes dos dois lados |


## Validação do lote (Passo 4)

| gate | comando | resultado |
|---|---|---|
| `check` | `make check` (lint + typecheck + arch + test) | **zero** — 277 testes de backend, 86 de frontend, cobertura de `core/` em 99,58% |
| `eval` | `EVAL_DOCUMENT_ID=ce4e9cd0-… make eval` | **zero** — NFR-7 atingido com `SIMILARITY_THRESHOLD=0.561` |
| compose | `docker compose up -d --build` + 4 perguntas contra a API real | ver abaixo |

### Reprodução manual depois do fix (API real, `document_id` `ce4e9cd0-…`)

| bug | pergunta | antes | depois |
|---|---|---|---|
| B5 | `Quem fundou a empresa?` | "consta na página 2 (Trechos 1 e 2)" | "o fundador (página 2)" — sem "Trecho N" |
| B1 | `e a formação dele?` | recusa; `should_condense` = `False`, `top_score` 0,527 | responde; `chat.condensed used_llm=true`, `top_score` **0,796** |
| B2 | `Qual o e-mail de contato?` | recusa, `top_score` 0,596 < 0,625 | responde `contato@exemplo.com.br (página 3)` |
| B2 | `O que é a sigla citada no documento?` | recusa, `top_score` 0,612 < 0,625 | responde, citando a página 2 |

B3 e B4 não têm reprodução contra a API: são texto de interface, cobertos por
teste de unidade no frontend (`CitationChip.test.tsx`, `errors.test.ts`) e no
backend (`test_gemini_adapter.py`). Forçar o B4 exigiria estourar de propósito a
cota diária de 20 gerações, que a `B.5` ainda precisa para gravar o vídeo.

## Nota de ambiente

O `.env` local foi sincronizado com o `.env.example` (`SIMILARITY_THRESHOLD=0.561`)
com autorização explícita do owner — a constitution universal proíbe tocar em
`.env` sem ela. Sem essa linha, o container continua rodando o corte antigo e o
B2 volta a aparecer, mesmo com o código corrigido. Quem clonar o projeto pega o
valor certo do `.env.example`.

## Verificação (`/double-check`, 2026-08-18)

Placar: **5 sanados (✓) · 0 não sanados (✗) · 0 inconclusivos (⚠)**.

A verificação não confiou nos testes do lote como prova: cada teste de regressão
foi reexecutado contra o **código de produção pré-fix** (cópia em scratchpad, com
`app/core/condensation.py`, `app/core/prompt.py`, `app/config.py`,
`app/adapters/gemini.py`, `eval/dataset.json`, `CitationChip.tsx`, `errors.ts` e o
`aria-label` do `MessageList.tsx` revertidos para o `HEAD`). Um teste que passa
nos dois estados não prova nada; os que provam são os que falharam antes.

| bug | como foi reproduzido hoje | resultado |
|---|---|---|
| B1 | `should_condense` sobre 10 entradas escritas do relato, incluindo a fronteira 3/4/5 palavras e o AC-3; 2 testes de regressão contra o código pré-fix; sequência real no compose | pré-fix: 2 testes **falham**. Hoje: `e a formação dele?` condensa, `chat.condensed used_llm=true`, `top_score` **0,796** (era 0,527), resposta correta. **✓** |
| B2 | `EVAL_DOCUMENT_ID=ce4e9cd0-… make eval` reexecutado hoje contra a API real (quota de embedding) + pergunta sem âncora no compose | eval **exit 0**, 23 itens, falsa recusa **0,000**, recusa correta **1,000**, `recall@3` 1,000, `MRR` 0,939, folga 0,526→0,596 e ponto médio 0,561 — números idênticos aos registrados. Ao vivo: `Qual o e-mail de contato?` responde com `top_score` **0,596** (o valor exato que 0,625 recusava). **✓** |
| B3 | 4 asserções de frontend contra o código pré-fix + inspeção do bundle servido pelo container | pré-fix: 4 testes **falham**. O bundle em `localhost:5173` carrega "Trecho consultado · página", "Trechos consultados para esta resposta" e o `aria-label` novo. FR-8/AC-10 descrevem o que o código emite. **✓** |
| B4 | teste de backend e de frontend contra o código pré-fix | pré-fix: os dois **falham** ("Espere um minuto…"). Hoje os dois textos cobrem as duas cotas. O `429` ao vivo **não** foi forçado — exigiria estourar de propósito a cota diária; o caminho `429 → limite_de_uso → texto` já é coberto pelos testes do AC-12. **✓** |
| B5 | instrução conferida no prompt montado + 3 respostas reais no compose | pré-fix: teste **falha**. Hoje a instrução está no prompt montado e nenhuma das três respostas reais citou "Trecho N" — todas citaram só a página. **✓** (obediência do modelo é observada, não garantida) |

### Suíte completa do projeto (Passo 4)

| gate | comando | resultado |
|---|---|---|
| `check` | `make check` | **zero** — ruff, eslint, mypy strict, tsc, `lint-imports` (4 contratos KEPT), 278 testes de backend, cobertura de `core/` **99,58%**. Rodado duas vezes: 86 testes de frontend na primeira e **111 na segunda**, porque o trabalho paralelo de identidade visual avançou durante a verificação; verde nas duas |
| `security` | `make security` | **zero** — bandit sem achado, `pip-audit` sem vulnerabilidade conhecida, `npm audit` 0 |
| `eval` | `EVAL_DOCUMENT_ID=ce4e9cd0-… make eval` | **zero** — NFR-7 atingido com `SIMILARITY_THRESHOLD=0.561` |
| compose | `docker compose ps` + 3 turnos reais | backend, frontend e db no ar; runtime do container em `threshold=0.561`, `top_k=5`, `chat_model=gemini-3.1-flash-lite` |

Nenhuma regressão colateral: os **389** testes (278 backend + 111 frontend)
passam com o trabalho paralelo de identidade visual no mesmo diff.

### Pendências levantadas pela verificação

Nenhum `✗` e nenhum `⚠`. Fica registrado um resíduo de documentação, fora do
escopo deste workflow (que não altera código de produção):

- Três comentários internos ainda usam o vocabulário que o B3 aposentou —
  `backend/app/chat.py:403` ("os chunks **usados**"), `backend/app/core/models.py:72`
  e `frontend/src/lib/types.ts:46` ("trecho que **sustentou** uma resposta"). Não
  reproduzem o bug (não são texto de interface), mas divergem de FR-8. Ação
  sugerida: acertar junto da próxima edição desses arquivos.
