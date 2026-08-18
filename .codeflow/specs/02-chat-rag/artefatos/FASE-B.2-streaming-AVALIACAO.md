---
spec: 02-chat-rag
fase: B.2
slug_fase: streaming
tentativa: 2
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: d1536f0..e696ab7
---

# FASE B.2 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

O gate pelo `docker compose` foi cumprido com instrumentação de verdade, e a
parte que eu podia refazer sozinha, refiz: abri um turno SSE **pelo nginx** e
conferi cabeçalho e formato de quadro contra o que o `sse.ts` espera. Casam.
Zero BLOQUEANTES, zero IMPORTANTES.

> **Nota sobre `range_avaliado`:** o EXECUCAO declara `d1536f0..e0d40d9`, a ponta
> da tentativa 1. Auditei o span real, que inclui o rework. Ver S-1 na `B.1`.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | Gate fechado com medição: quadros em 3,244 / 3,304 / 3,348 s pelo nginx e o balão crescendo 40 → 77 → 184 → 352 chars; primeiro token 3,244 s (AC-23 ≤ 5 s); "Parar resposta" encerrou o turno com parcial gravada `truncated=true` e **sem** `chat.generated`. Escopo travado: `grep -rn EventSource src/` → 0; sem `AbortController` órfão; buffer não assume chunk = quadro |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `sse.ts` parser puro, `useChat.ts` estado, `api.ts` dono do transporte. O efeito de limpeza passou a depender do `conversationId` (`useChat.ts:99`), fechando a brecha que eu apontei |
| 3 | Segurança / LGPD | 3 | 5 | Payload fora do contrato descartado, agora **sem default nenhum** (`sse.ts:33-38`); código desconhecido cai em `erro_interno`; grep de segredo → 0 |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `ApiError`, `readErrorEnvelope`, `BASE_URL`, `getSessionId` reusados; nenhuma frase de erro nova; zero dependência |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Eventos tipados espelhando a §4.3 literalmente; conferi contra o fio real (§6) |
| 6 | Local e nomes dos arquivos | 2 | 4 | `openChatStream` segue em `api.ts` — desvio declarado desde a tentativa 1, e continua sendo a escolha certa (a alternativa duplicaria o cliente HTTP) |
| 7 | Qualidade de código | 2 | 5 | A normalização de `\r\n` passou a rodar sobre o buffer concatenado (`sse.ts:142-146`), que é onde a defesa tem efeito |
| 8 | Testes e cobertura | 2 | 5 | Os dois testes novos do parser (par `\r\n` partido entre chunks; citação incompleta descartada) **falham contra a versão anterior** — verificado pelo executor e coerente com o diff. A lacuna "nenhum teste cobre `fetch → parser → tela`" fechou pelo caminho certo: o gate real, não um mock a mais |
| 9 | Migration safety | 2 | — | Não se aplica |

Média ponderada: 98/20 = 4,9 → **9.8/10**.

## 3. Achados BLOQUEANTES

Nenhum. O B-1 da tentativa 1 está fechado.

**O que eu mesma verifiquei contra o compose no ar**, num turno de recusa (que
não gasta o modelo de chat), pelo `:5173`:

```text
HTTP/1.1 200 OK
Server: nginx/1.27.5
Content-Type: text/event-stream; charset=utf-8
Transfer-Encoding: chunked
cache-control: no-cache

event: token
data: {"text": "Não encontrei essa informação no documento enviado. …"}

event: citations
data: {"citations": []}

event: done
data: {"message_id": 73, "truncated": false}
```

Três coisas ficam provadas aí, sem depender do relatório: o `Content-Type` é
exatamente o que `api.ts:190` procura com `.includes('text/event-stream')`; o
quadro é `event: <nome>\ndata: <json>\n\n`, que é o que `sse.ts:144` fatia; e a
resposta sai `chunked`, sem buffer intermediário. O `x-accel-buffering: no` não
aparece no `:5173` porque o nginx o **consome** — exatamente como o relatório
diz —, e `frontend/nginx.conf:29` tem `proxy_buffering off` com
`proxy_read_timeout 300s`. Risco 3 da spec, descartado.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **Ver S-1 e S-2 na avaliação da `B.1`** (frontmatter fora do schema; linha
  "Não se aplica — primeira execução." sobrando no §8 deste relatório,
  `FASE-B.2-streaming-EXECUCAO.md:180`).
- **`buffer = (buffer + decoded).replace(...)` re-varre o buffer inteiro a cada
  chunk** (`sse.ts:146`). Correto e barato aqui, porque o buffer é drenado a
  cada quadro; só vale lembrar que a conta muda se algum dia um quadro passar a
  ser grande.
- **Achado do executor para a `A.4`, e ele procede:** `chat.client_disconnected`
  (§4.6) não é emitido no cancelamento real — sob uvicorn a desconexão chega
  como cancelamento da task e o `finally` grava a parcial sem passar pelo
  `is_disconnected()`. FR-12 acontece; o registro em log, não. É da `A.4`, e
  não retém esta fase.

## 6. Comandos rodados + saídas reais

```text
$ make check
Contracts: 4 kept, 0 broken.
===================== 263 passed, 19 deselected in 14.35s ======================
 Test Files  10 passed (10)
      Tests  84 passed (84)

$ make security
No known vulnerabilities found | found 0 vulnerabilities | SEC_EXIT=0

$ grep -rn "EventSource" frontend/src | wc -l
0

$ grep -n "proxy_buffering\|proxy_read_timeout" frontend/nginx.conf
29:        proxy_buffering off;
31:        proxy_read_timeout 300s;

# turno SSE real pelo nginx (caminho de recusa: não chama o modelo de chat)
$ curl -sN -i -X POST http://localhost:5173/api/conversations/<id>/messages \
    -H 'Accept: text/event-stream' -d '{"question":"qual a cotacao do dolar …?"}'
HTTP/1.1 200 OK … Content-Type: text/event-stream; charset=utf-8 … chunked
event: token / event: citations / event: done      (saída completa na §3)

$ git status --short
(só um arquivo do Track A, de chat paralelo; nada meu)
```

## 7. Itens da fase / DoD não atendidos

Nenhum. Os três itens abertos na tentativa 1 fecharam:

- streaming token a token pelo compose ✅ (medido, e o transporte conferido por mim);
- "cancelar interrompe de fato" ✅ — agora provado **contra o servidor**: parcial
  gravada com `truncated=true` e nenhum `chat.generated` no turno. Confirmei o
  padrão no banco: mensagens `#40/#41/#42` com `truncated = t` e 5 citações;
- AC-23 ✅ (3,244 s).

## 8. Divergências entre o relatório e o código real

- **A de S-1** (`range` desatualizado).
- **Nenhuma outra.** Verifiquei uma a uma as afirmações do §10: o `Content-Type`,
  o formato do quadro, o `proxy_buffering off` e a persistência da parcial com
  `truncated=true`. Todas conferem.
