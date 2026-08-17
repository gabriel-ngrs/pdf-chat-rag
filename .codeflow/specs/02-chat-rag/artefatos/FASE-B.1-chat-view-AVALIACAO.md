---
spec: 02-chat-rag
fase: B.1
slug_fase: chat-view
tentativa: 1
veredito: REPROVADO
score: 9.0
threshold: 8.5
range_avaliado: dd621eb..28159b6
---

# FASE B.1 — Avaliação independente

## 1. Veredito e score

**Veredito:** REPROVADO · **Score:** 9.0 / threshold 8.5

Score acima do threshold, código de qualidade alta e escopo travado respeitado
em todos os itens verificáveis. Reprova por **um BLOQUEANTE**: o critério de
conclusão declarado na §5 da spec — *"conversa criada contra o backend real"* —
não foi cumprido. Pela cascata de §2.10.3, BLOQUEANTE reprova qualquer que seja
o score.

O bloqueio é de **verificação, não de código**. Auditei o contrato do cliente
contra a `A.4`, que já está na `dev` (`9f0a2b1`, mergeada em `5acdb26`), e ele
casa campo a campo. O caminho de fechamento é rodar o compose, não reescrever a
fase.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 3 | AC-16 provado offline (`ChatView.test.tsx:135` cria 1 conversa sob `StrictMode`); AC-29 parcial (`MessageList.tsx:200-206` `aria-live` desde o 1º render; `MessageInput.tsx:67` `<label>`). Escopo travado 100%: `grep -nE "#[0-9a-fA-F]{3,6}\|(text\|bg\|border)-(gray\|slate\|zinc\|...)-[0-9]"` → 0; `grep -nE "zustand\|redux\|jotai\|recoil\|mobx" package.json` → 0. **Gate de conclusão não cumprido** (ver §3) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | Separação `components/`/`hooks/`/`lib/` da constitution respeitada; `ChatView.tsx:10` importa só de `@/lib/api`, nenhum `fetch` novo (`api.ts:133-144` passa pelo `request()` da FEAT-0001) |
| 3 | Segurança / LGPD | 3 | 5 | `grep -rniE "gemini_api_key\|sk-[a-z0-9]{10}" src/` → 0; o `localStorage` guarda só dois ids (`ChatView.tsx:22-25`), nenhum conteúdo de documento; erro sai por `code` (`ChatView.tsx:96`), nunca por texto do servidor |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `createConversation`/`listMessages` sobre o `request()` existente, herdando `X-Session-Id`, timeout e leitura do envelope; tokens e `ScrollArea`/`Button`/`Skeleton` do design system da FEAT-0001 B.1; zero dependência nova |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Identificadores em inglês, textos de UI em pt-BR (`MessageInput.tsx:68,78`); tipos derivados da §4.4 com nomes de campo em `snake_case` como o JSON (`types.ts:60-74`) |
| 6 | Local e nomes dos arquivos | 2 | 4 | Os três componentes exatamente onde a §5 manda; `ProcessingStatus.tsx` alterado fora da lista — desvio declarado e justificado (§5 do EXECUCAO, decisão 5), prop opcional de 3 linhas |
| 7 | Qualidade de código | 2 | 5 | Funções curtas; comentários registram o "porquê" não-óbvio (`ChatView.tsx:82-85` sobre a bandeira de cancelamento no `StrictMode`), nunca o "o quê" |
| 8 | Testes e cobertura | 2 | 4 | 10 testes novos, todos offline e determinísticos; o acompanhamento de scroll (`MessageList.tsx:34-62`) fica sem teste — justificado (jsdom não faz layout), mas é comportamento não coberto |
| 9 | Migration safety | 2 | — | Não se aplica: a fase não toca schema |

Média ponderada dos oito aplicáveis: 90/20 = 4,5 → **9.0/10**.

## 3. Achados BLOQUEANTES

### B-1. Critério de conclusão da fase não cumprido — "conversa criada contra o backend real"

**Onde:** `SPEC_02_CHAT_RAG.md` §5, Fase B.1, *Critério de conclusão (gate)*;
`FASE-B.1-chat-view-EXECUCAO.md:150` marca o item como PENDENTE.

O gate da fase tem três partes: (a) conversa criada contra o backend real,
(b) campo utilizável, (c) layout consistente com o design system **nos dois
temas**. Nenhuma das três foi verificada contra o app rodando — a `A.4` não
existia no momento da execução, e a conferência visual dos dois temas ficou
junto.

O executor foi honesto: não simulou, não deu por cumprido, e a `B.1` da FEAT-0001
tem o precedente inverso (reprovada justamente por cumprir gate contra stub). O
que não se pode fazer é **concluir** a fase com o gate aberto — só `APROVADO`
conclui, e concluir libera as dependentes (ARTIFACTS_SPEC §2.11.4).

**Correção sugerida (não exige mudar código):**
1. `make up` com a `dev` atual (a `A.4` já está lá, `9f0a2b1`), enviar o
   `Exemplo-YAITEC.pdf`, esperar `ready`.
2. Confirmar no DevTools **um** `POST /api/conversations` → `201 {"id": ...}`, o
   campo habilitado, e o mesmo id reaproveitado após `F5`.
3. Alternar claro/escuro e conferir a tela nos dois.
4. Registrar as evidências no EXECUCAO (tentativa 2) e reavaliar em chat zerado.

**Nota de contrato:** auditei o cliente contra a `A.4` real e ele casa —
`ConversationCreateRequest.document_id` ↔ `api.ts:137`;
`ConversationResponse.id` ↔ `types.ts:73`; `MessageResponse` ↔ `ChatMessage`
campo a campo, com `MessageRole` (`core/models.py:66-67`) valendo exatamente
`'user' | 'assistant'` do `types.ts:58`. A expectativa é que o gate feche sem
retrabalho.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **`useChat` descarta o histórico do servidor quando a pessoa pergunta antes de
  ele chegar** (`hooks/useChat.ts:67-68`, introduzido na B.4 mas nascido da
  restauração desta fase): `setMessages((current) => (current.length === 0 ? history : current))`.
  Perguntar nos primeiros milissegundos após o `F5` faz o histórico anterior
  sumir da tela pelo resto da sessão. Mesclar por `id` em vez de descartar
  resolveria sem reintroduzir o risco que o guard evita.
- **Chips de pergunta sugerida ficam clicáveis quando a conversa falhou**
  (`ChatView.tsx:203-214`): com `conversation.status === 'failed'` o
  `emptyState` continua renderizado, e o clique cai no `return` mudo de
  `useChat.ts:95`. Ou desabilitar os chips junto com o campo, ou trocar o
  `emptyState` por um convite a recarregar.
- **A decisão de acompanhar o fim da lista poderia ser uma função pura**
  (`MessageList.tsx:43-45`), recebendo os três números e devolvendo booleano —
  fecharia a única lacuna de teste da fase sem inflar abstração.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ ids de fase únicos (12 fases)
✓ heading de cada fase casa com o bullet `id`
✓ todos os slugs são kebab-case
✓ wave: multi com ao menos um id `<TRACK>.<n>`
✓ todo `id` em "Depende de" existe na §5
✓ cada track tem 3–8 fases
✓ grafo de dependências acíclico
✓ §5 estruturalmente válida
EXIT=0

$ git merge-base --is-ancestor 28159b6 HEAD && echo ANCESTOR-OK
ANCESTOR-OK      # idem dd621eb; a `dev` contém o range inteiro

$ make check
...
Contracts: 4 kept, 0 broken.
cd backend && uv run pytest
Required test coverage of 90% reached. Total coverage: 99.55%
===================== 248 passed, 17 deselected in 11.93s ======================
cd frontend && npm run test
 Test Files  10 passed (10)
      Tests  75 passed (75)

$ make security
cd backend && uv run bandit -q -r app
cd backend && uv run pip-audit
No known vulnerabilities found
cd frontend && npm audit --audit-level=high
found 0 vulnerabilities
SECURITY_EXIT=0

# escopo travado da B.1 (esperado: 0 em todos)
$ grep -rn "EventSource" frontend/src | wc -l                              → 0
$ grep -rniE "gemini_api_key|sk-[a-z0-9]{10}" frontend/src | wc -l         → 0
$ grep -nE "#[0-9a-fA-F]{3,6}|(text|bg|border)-(gray|slate|zinc|neutral|stone|red|blue|green|purple)-[0-9]" \
    frontend/src/components/{ChatView,MessageList,MessageInput}.tsx        → 0
$ grep -nE "zustand|redux|jotai|recoil|mobx" frontend/package.json | wc -l → 0

# contraste dos pares usados nesta fase (WCAG AA; cálculo OKLCH→sRGB→relativa)
LIGHT secondary-fg-on-secondary        12.80:1   (balão da pergunta)
DARK  secondary-fg-on-secondary        13.04:1
LIGHT muted-fg-on-bg                    7.13:1   (rótulo "Resposta", metadados)
DARK  muted-fg-on-bg                    7.71:1
LIGHT ring-on-bg (alvo 3:1)             4.27:1   (foco do campo)
DARK  ring-on-bg (alvo 3:1)             8.12:1

$ git status --short
(vazio — árvore limpa ao final)
```

## 7. Itens da fase / DoD não atendidos

- **Gate da §5:** "conversa criada contra o backend real" — não cumprido (B-1).
- **Gate da §5:** "layout consistente com o design system **nos dois temas**" —
  provado por construção (só tokens), não por conferência visual. Os pares de
  contraste medidos acima passam AA, o que remove o risco, mas a conferência
  visual continua devendo.
- **Elegibilidade (ARTIFACTS_SPEC §2.11.4):** a `B.1` declara `Depende de: A.4`,
  e a `A.4` não estava concluída (não existia) quando a fase rodou. A instrução
  verbal de paralelizar não substitui o gate — a constitution universal exige
  decision arquitetural registrada **antes** da invocação, e
  `.codeflow/decisions/INDEX.md` não tem nenhuma sobre isso. Não é achado contra
  o código; é a causa do B-1 e vale registrar para as próximas paralelizações.
- **DoD §9 da spec:** "`B.1 chat-view` — conversa criada uma única vez" ✅
  (provado); "layout consistente nos dois temas" ⏳.

## 8. Divergências entre o relatório e o código real

Nenhuma divergência material. Confirmei ponto a ponto:

- "conversa criada **1 vez** sob `StrictMode`" — confere (`ChatView.test.tsx:145`).
- "nenhum `fetch` novo" — confere (`api.ts:133-144` usa `request()`).
- "nenhuma cor própria" — confere (grep 0).
- "`ProcessingStatus.onReady` é o único arquivo fora da lista" — confere
  (`git diff --stat dd621eb..28159b6` lista 9 arquivos; os outros 8 estão na §5
  ou são testes).
- O relatório marca os itens pendentes como pendentes, sem inflar. É o padrão
  correto e vale dizer: **nada foi declarado cumprido sem estar**.
