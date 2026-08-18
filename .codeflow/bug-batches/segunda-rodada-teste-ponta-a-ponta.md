---
versão: 1.0
lote: segunda-rodada-teste-ponta-a-ponta
origem: .codeflow/bugs/INDEX.md e relatos .codeflow/bugs/006–010 (instruções do owner nesta conversa)
criado: 2026-08-18
atualizado: 2026-08-18
placar: 5 corrigido, 0 bloqueado, 0 não-reproduz
verificação: 5 sanados (✓), 0 não sanados (✗), 0 inconclusivos (⚠) — /double-check de 2026-08-18
---

# Lote `segunda-rodada-teste-ponta-a-ponta`

Cinco defeitos encontrados na segunda rodada automatizada do teste de ponta a
ponta. O owner decidiu: progresso suavizado para ingestões rápidas (BUG-008) e
timeout máximo de condensação de 5 s para 2 s (BUG-009).

## Bugs

| id | título | status | repro/teste | fix (arquivo:linha) | decision | verificação |
|----|--------|--------|-------------|---------------------|----------|-------------|
| B6 | Conversa longa rola a página e esconde o campo | corrigido | `frontend/src/components/AppShell.test.tsx` + repro manual: conversa com 10 perguntas em viewport de 900 px; formulário permanece visível e a lista interna transborda | `frontend/src/components/AppShell.tsx:138` | 2026-08-18-segunda-rodada-de-correcoes-do-teste-de-ponta-a-ponta.md | ✓ (2026-08-18) |
| B7 | Pergunta longa recebe mensagem de PDF inválido | corrigido | `backend/tests/test_errors.py::test_erro_de_validacao_do_framework_sai_no_envelope` + `frontend/src/lib/errors.test.ts` → pergunta longa | `backend/app/errors.py:48`, `frontend/src/lib/errors.ts:53` | 2026-08-18-segunda-rodada-de-correcoes-do-teste-de-ponta-a-ponta.md | ✓ (2026-08-18) |
| B8 | Barra de progresso não avança no PDF de exemplo | corrigido | `frontend/src/components/ProcessingStatus.test.tsx` → avanço estimado com primeiro lote pendente | `frontend/src/components/ProcessingStatus.tsx:121` | 2026-08-18-segunda-rodada-de-correcoes-do-teste-de-ponta-a-ponta.md | ✓ (2026-08-18) |
| B9 | Condensação espera 5 s no fallback | corrigido | `backend/tests/test_config.py::test_timeout_de_condensacao_prioriza_o_fallback_rapido` | `backend/app/config.py:57`, `.env.example:56` | 2026-08-18-segunda-rodada-de-correcoes-do-teste-de-ponta-a-ponta.md | ✓ (2026-08-18) |
| B10 | Turno interrompido não registra evento de fecho | corrigido | `backend/tests/test_chat_api.py::test_cancelamento_do_gerador_registra_o_fecho_do_turno` | `backend/app/chat.py:113,320` | ✓ (2026-08-18) |

## Fila e escopo esperado (Passo 2)

| ordem | id | fase dona | escopo esperado |
|---|---|---|---|
| 1 | B6 | B.1 | `frontend/src/components/AppShell.tsx`; reprodução manual em navegador real (jsdom não calcula o layout) |
| 2 | B7 | A.1 + B.2 | `backend/app/errors.py`, testes de API/erros, `frontend/src/lib/errors.ts` e teste |
| 3 | B8 | A.4 | `frontend/src/components/ProcessingStatus.tsx` e teste; possivelmente `frontend/src/hooks/useDocumentStatus.ts` e teste |
| 4 | B9 | A.2 | `backend/app/config.py`, `backend/tests/test_config.py` e `.env.example` somente se a configuração documentada precisar refletir o novo default |
| 5 | B10 | A.4 | `backend/app/chat.py`, `backend/tests/test_chat_api.py` e/ou `backend/tests/test_logging.py` |

## Verificação — 2026-08-18

- **B6:** Chromium real em 1440×900: viewport da conversa com `scrollHeight`
  4386 e `clientHeight` 603; página em 900 px e formulário com base em 823 px.
- **B7:** `POST` com pergunta de 3.000 caracteres respondeu `422` com
  `code: entrada_invalida`; a descrição da interface cobre o limite de 2.000.
- **B8:** upload real do `Exemplo-YAITEC.pdf` mostrou os valores estimados 0%,
  67% e 86% antes de o documento ficar pronto.
- **B9:** o default de condensação é 2 s, confirmado pelo teste de regressão.
- **B10:** fechar o gerador após o primeiro token gera `chat.generated` com
  `truncated: true`, confirmado pelo teste de regressão.
