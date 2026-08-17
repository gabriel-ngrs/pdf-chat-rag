---
spec: 02-chat-rag
fase: B.2
slug_fase: streaming
tentativa: 1
veredito: REPROVADO
score: 9.0
threshold: 8.5
range_avaliado: d1536f0..e0d40d9
---

# FASE B.2 — Avaliação independente

## 1. Veredito e score

**Veredito:** REPROVADO · **Score:** 9.0 / threshold 8.5

É a fase mais bem construída do track: o parser de SSE é testado sobre bytes de
verdade (quadro partido, multibyte cortado, quadro final sem `\n\n`), e as duas
conferências pré-parser exigidas por FR-11 estão no lugar certo. Reprova por
**um BLOQUEANTE**: o critério de conclusão — *"resposta real renderiza token a
token **através do `docker compose`**"* — não foi cumprido.

Auditei o parser contra o formato de fio que a `A.4` realmente emite
(`fastapi.sse.format_sse_event`, separador `\n`, keep-alive `: ping\n\n`) e o
cliente casa. O fechamento é execução do gate, não retrabalho.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 3 | AC-2 e AC-17 provados (`ChatView.test.tsx:215-243` observa `A YAITEC` antes de `A YAITEC oferece consultoria.` — falharia se o cliente esperasse o stream inteiro); AC-12 pré e mid-stream (`:264`, `:281`). Escopo travado 100%: `grep -rn EventSource src/` → 0; `AbortController` abortado no desmonte (`useChat.ts:81-86`); buffer não assume chunk = quadro (`sse.ts:129-140`). **Gate do compose não cumprido** (§3) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `sse.ts` é parser puro sobre `Response`; `useChat.ts` guarda estado; `api.ts` é dono do `fetch` e dos segredos do transporte. Nenhuma inversão |
| 3 | Segurança / LGPD | 3 | 5 | Payload fora do contrato é descartado em vez de virar `undefined` circulando (`sse.ts:16-37,51-72`); código de erro desconhecido cai em `erro_interno` (`sse.ts:59`); nenhum segredo no diff (grep 0) |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `ApiError`, `readErrorEnvelope`, `BASE_URL` e `getSessionId` reusados (`api.ts:158-195`); nenhuma frase de erro nova — os códigos vêm do mapa de `errors.ts`; zero dependência nova |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Eventos tipados espelhando §4.3 literalmente (`sse.ts:10-14`); textos pt-BR, identificadores em inglês |
| 6 | Local e nomes dos arquivos | 2 | 4 | `sse.ts` e `useChat.ts` como a §5 manda; `openChatStream` foi para `api.ts` em vez de `sse.ts` — desvio declarado, e é a escolha certa: a alternativa exportaria três internos do cliente HTTP para o `sse.ts` refazer a mesma chamada |
| 7 | Qualidade de código | 2 | 5 | `parseFrame`/`toEvent`/`readCitations` pequenas e de responsabilidade única; o "porquê" registrado onde é contraintuitivo (`useChat.ts:44-47` sobre acumular em variável local, não no estado) |
| 8 | Testes e cobertura | 2 | 4 | 12 testes novos, 8 deles sobre bytes reais; mas os testes de tela mockam `parseChatStream` (`ChatView.test.tsx:20`), então **nenhum teste cobre `fetch → parser → tela`** de ponta a ponta. Declarado no EXECUCAO §9.2 |
| 9 | Migration safety | 2 | — | Não se aplica |

Média ponderada: 90/20 = 4,5 → **9.0/10**.

## 3. Achados BLOQUEANTES

### B-1. Critério de conclusão da fase não cumprido — streaming pelo `docker compose`

**Onde:** `SPEC_02_CHAT_RAG.md` §5, Fase B.2, *Critério de conclusão (gate)*;
`FASE-B.2-streaming-EXECUCAO.md:139` marca PENDENTE.

O gate tem três partes: resposta real token a token **pelo compose** (não pelo
dev server), cancelar interrompendo de fato, e lint/typecheck zero. Só a terceira
foi cumprida. A exigência de ser pelo compose não é formalidade: é o Risco 3 da
spec (buffering matando o streaming), e o único lugar onde o `proxy_buffering
off` do nginx e o `X-Accel-Buffering: no` do backend são exercitados juntos.

**Correção sugerida (sem mudar código):**
1. `make up` na `dev` atual, ingerir o `Exemplo-YAITEC.pdf`.
2. Perguntar e confirmar **na aba Network** que o corpo cresce ao longo do tempo
   (não chega inteiro), e que o `Content-Type` é `text/event-stream`.
3. Clicar em "Parar resposta" no meio e confirmar no log do backend o evento
   `chat.client_disconnected` (`chat.py`), que é a contraparte servidor do
   cancelamento.
4. Medir o primeiro token (AC-23, ≤ 5 s) — é o mesmo round-trip.
5. Registrar no EXECUCAO (tentativa 2) e reavaliar em chat zerado.

**Nota de contrato (conferida por mim, favorável):** o servidor usa
`format_sse_event` com separador `\n` e `lines.append("")` duplo, ou seja,
quadros `event: <nome>\ndata: <json>\n\n` — exatamente o que `sse.ts:131-140`
procura. O keep-alive é `: ping\n\n`, que cai no `line.startsWith(':')` de
`sse.ts:86` e no `data.length > 0` de `sse.ts:99`, sendo ignorado como deve.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **A normalização de `\r\n` é feita por chunk, não sobre o buffer**
  (`sse.ts:129`): um `\r` que termine um chunk e um `\n` que comece o seguinte
  escapam da troca. Como o servidor deste projeto emite `\n` puro, hoje é caminho
  morto; se a defesa é para valer contra proxy, ela precisa rodar depois do
  `buffer +=`, não antes.
- **`readCitations` fabrica `chunk_index: 0` e `score: 0`** quando os campos
  faltam (`sse.ts:32-33`). O `score` é exibido ao usuário ("similaridade 0,00",
  `CitationChip.tsx:63`), então o default vira um número inventado na tela.
  Descartar a citação incompleta — como já se faz quando falta `page_number` —
  seria coerente com o escopo travado "não fabricar citação" da B.3.
- **Trocar `conversationId` não aborta o stream em curso** (`useChat.ts:81-86`,
  deps `[]`). Hoje é inalcançável (trocar de documento desmonta a `ChatView`),
  mas o dia em que a tela sobreviver à troca, o stream antigo continua.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ §5 estruturalmente válida
EXIT=0

$ git merge-base --is-ancestor e0d40d9 HEAD && echo ANCESTOR-OK
ANCESTOR-OK      # idem d1536f0

$ make check
Contracts: 4 kept, 0 broken.
Required test coverage of 90% reached. Total coverage: 99.55%
===================== 248 passed, 17 deselected in 11.93s ======================
cd frontend && npm run test
 Test Files  10 passed (10)
      Tests  75 passed (75)

$ make security
No known vulnerabilities found
found 0 vulnerabilities
SECURITY_EXIT=0

# escopo travado da B.2
$ grep -rn "EventSource" frontend/src | wc -l   → 0
$ grep -c "^\s*it(" frontend/src/lib/sse.test.ts → 8

# formato de fio que o servidor realmente emite (fastapi 0.141.1)
$ sed -n '212,237p' backend/.venv/.../fastapi/sse.py
    lines.append(f"event: {event}")
    ... lines.append(f"data: {line}")
    lines.append(""); lines.append("")
    return "\n".join(lines).encode("utf-8")
KEEPALIVE_COMMENT = b": ping\n\n"
# → separador `\n`, quadro terminado em `\n\n`: casa com sse.ts:131

$ git status --short
(vazio — árvore limpa ao final)
```

## 7. Itens da fase / DoD não atendidos

- **Gate da §5:** resposta real token a token pelo `docker compose` — não
  cumprido (B-1).
- **Gate da §5:** "cancelar interrompe de fato" — provado no cliente
  (`ChatView.test.tsx:245`), não contra o servidor (FR-12, evento
  `chat.client_disconnected`).
- **AC-23 (NFR-1, primeiro token ≤ 5 s)** — não medido. É gate nominal da `A.4`,
  mas só é observável pelo cliente, e o mesmo round-trip do B-1 o fecha.
- **DoD §9 da spec:** "`B.2 streaming` — resposta token a token pelo compose;
  cancelar interrompe" ⏳.
- **Elegibilidade (§2.11.4):** a `B.2` depende da `B.1`, que não está concluída;
  e o track inteiro correu antes da `A.4`. Ver B-1 da avaliação da `B.1`.

## 8. Divergências entre o relatório e o código real

Nenhuma divergência material.

- "grep -r EventSource não encontra nada" — confirmado por mim, 0 ocorrências.
- "o `finally` do gerador cancela o `reader`" — confirmado (`sse.ts:148-150`) e
  provado pelo teste `sse.test.ts:115`.
- "`openChatStream` em `api.ts` é o único desvio de arquivo" — confirmado pelo
  `git diff --stat d1536f0..e0d40d9` (7 arquivos; os demais são os da §5 e testes).
- "nenhuma mensagem de erro nova foi escrita nesta fase" — confirmado: o diff de
  `errors.ts` neste range é vazio.
