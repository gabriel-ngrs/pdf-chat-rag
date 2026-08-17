---
spec: 02-chat-rag
fase: B.2
slug_fase: streaming
status: executado
tentativa: 2
reprovacoes: 1
sha_inicial: d1536f0
sha_final: e0d40d9
range: d1536f0..e0d40d9
---

# FASE B.2 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/Yaitec-TalkDoc-chatB`, branch
> `feat/chat-rag-trackB`.

## ⚠️ O gate "pelo `docker compose`" continua PENDENTE

Mesma situação da `B.1`: a `A.4` não existe ainda, então "resposta real renderiza
token a token através do `docker compose`" **não foi cumprido** — não foi
simulado nem marcado como cumprido. O que existe é o cliente inteiro, provado
contra o contrato da §4.3 com quadros SSE reais (bytes, chunks cortados,
multibyte partido), não contra um mock do parser.

## 1. Resumo do que foi feito

A pergunta vai ao servidor por `POST` e a resposta aparece token a token. Entre o
envio e o primeiro token a tela mostra "pensando"; durante a geração há um botão
de parar; o que já chegou é preservado quando a pessoa cancela ou quando o
provedor falha no meio. Erro **antes** do primeiro byte é tratado como resposta
HTTP normal — nunca entra no parser de SSE.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `frontend/src/lib/sse.ts` | Transforma o corpo da resposta em eventos tipados e validados (`token`, `citations`, `error`, `done`) |
| `frontend/src/hooks/useChat.ts` | O turno de conversa: envio otimista, acúmulo dos tokens, fechamento da mensagem, cancelamento |
| `frontend/src/lib/sse.test.ts` | 8 testes do parser, sobre bytes de verdade |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `frontend/src/lib/api.ts` | `openChatStream()`: `POST` sem timeout, com as duas conferências pré-parser (status e `Content-Type`) |
| `frontend/src/components/ChatView.tsx` | Passa a usar `useChat`; botão "Parar resposta" durante a geração |
| `frontend/src/components/MessageList.tsx` | Renderiza a resposta em construção e o indicador de "pensando" |
| `frontend/src/components/ChatView.test.tsx` | +4 testes de streaming (incremental, cancelamento, erro pré e mid-stream) |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `ApiError`, `readErrorEnvelope`, `BASE_URL` e
`getSessionId()` são os da `FEAT-0001` — o `openChatStream` não repete nenhum
deles. O aviso de erro sai por `notify.error(code)`, com as frases de
`errors.ts`; nenhuma mensagem de erro nova foi escrita nesta fase (os códigos
novos entram na `B.4`, que é dona disso). `Skeleton` e `Button` vêm do design
system. Nenhuma dependência nova.

**Decisões de design:**

1. **`openChatStream` foi para `api.ts`, não para `sse.ts`.** A §5 lista só
   `ChatView.tsx` como alterado nesta fase — **desvio declarado**. A razão: o
   `sse.ts` da spec "recebe uma `Response`", ou seja, alguém antes dele faz o
   `fetch`; e esse alguém precisa de `BASE_URL`, do `X-Session-Id` e do leitor de
   envelope de erro, que são privados do `api.ts`. A alternativa seria exportar
   três internos do cliente HTTP para o `sse.ts` reimplementar a mesma chamada —
   duplicação de fato, para respeitar uma lista de arquivos.
2. **Sem timeout no stream.** O `request()` tem timeout de 15 s, correto para
   JSON e errado para uma resposta que legitimamente demora. Quem corta é o
   `AbortSignal` — de quem cancelou ou de quem saiu da tela.
3. **A resposta em construção vive fora da lista de mensagens.** Se fosse o
   último item do histórico, cada token reescreveria esse item e a região
   `aria-live` anunciaria a resposta letra por letra. Do jeito que está, o item
   em construção é `aria-live="off"` e o anúncio acontece **uma vez**, quando a
   mensagem pronta entra na lista.
4. **O conteúdo é acumulado em variável local, não lido do estado.** O estado do
   React é assíncrono; fechar a mensagem a partir dele perderia os últimos
   tokens. A variável local é a fonte, o estado é só o espelho da tela.
5. **Evento desconhecido é ignorado, payload fora do contrato é descartado.** O
   que chega pela rede é `unknown`. Um `citations` sem `page_number` não pode
   virar `undefined` circulando até estourar num componente distante — e o
   keep-alive do servidor cai na mesma regra, sem tratamento especial.
6. **O parser normaliza `\r\n`.** Nada no caminho garante LF puro (proxy,
   biblioteca, plataforma), e um `\r` sobrando quebraria a separação de quadros
   de um jeito difícil de enxergar.

## 5. Comandos rodados + saídas reais

```text
# testes do parser de SSE
$ npx vitest run src/lib/sse.test.ts
 Test Files  1 passed (1)
      Tests  8 passed (8)

# testes da tela (inclui os 4 novos de streaming)
$ npx vitest run src/components/ChatView.test.tsx
 Test Files  1 passed (1)
      Tests  11 passed (11)

# gate agregador
$ make check
cd backend && uv run ruff check .
cd frontend && npm run lint
cd backend && uv run mypy app
cd frontend && npx tsc --noEmit
cd backend && uv run lint-imports --config .importlinter
cd backend && uv run pytest
...
====================== 135 passed, 6 deselected in ... ======================
cd frontend && npm run test
 Test Files  9 passed (9)
      Tests  62 passed (62)
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-2** (FR-2, FR-16) — "mostra 'pensando' e depois a resposta chegando aos
  poucos": depois do primeiro token a tela mostra `A YAITEC`, e só depois do
  segundo mostra `A YAITEC oferece consultoria.` — a asserção falharia se o
  cliente esperasse o stream inteiro.
- [x] **AC-17** (FR-16) — o mesmo teste confirma "Pensando na resposta." antes do
  primeiro token e sua saída **no primeiro token** (não no fim); o teste
  "cancela a resposta em andamento" confirma que o botão some, o texto recebido
  fica e o campo volta a ser utilizável.
- [x] **AC-12, parte pré-stream** (FR-11) — "trata erro antes do primeiro evento
  como aviso": `openChatStream` rejeita com `429`/`limite_de_uso`, o aviso sai
  com o título do mapa por código ("Limite de uso atingido"),
  `parseChatStream` **não** é chamado e a lista fica só com a pergunta.
- [x] **AC-12, parte mid-stream** — evento `error` depois de um token: aviso
  disparado e o texto recebido preservado.
- [x] **Buffer que lida com quadro cortado** — `sse.test.ts`: quadro partido em
  três chunks; caractere multibyte partido no meio do `ç` (o teste corta os bytes
  na mão); último quadro sem `\n\n` final.
- [x] **Não usar `EventSource`** — `grep -r EventSource frontend/src` não
  encontra nada; o consumo é `fetch` + `getReader()` + `TextDecoder`.
- [x] **`AbortController` sem ficar órfão** — abortado no cancelamento e no
  desmonte (`useEffect` de limpeza em `useChat`); o `finally` do gerador cancela
  o `reader`, provado pelo teste "fecha a leitura quando quem consome desiste no
  meio" (o `cancel` do `ReadableStream` é chamado uma vez).
- [ ] **Critério de conclusão — "resposta real renderiza token a token através do
  `docker compose`"**: **PENDENTE**, `A.4` não implementada.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (12 novos nesta fase; 62 no frontend)
- [x] `make check` zero
- [x] Escopo travado respeitado: não espera o stream inteiro; sem `EventSource`;
      sem `AbortController` órfão; não assume chunk = quadro
- [x] Nenhum segredo no diff
- [x] Commits em pt-BR, Conventional Commits (`e0d40d9`)
- [ ] Gate pelo compose — **pendente da `A.4`**

## 8. (Em rework) O que mudou nesta tentativa

Rework da avaliação `FASE-B.2-streaming-AVALIACAO.md` (tentativa 1, REPROVADO,
score 9,0). Sem BLOQUEANTE de código: o único é o gate pelo `docker compose`,
que continua aberto (topo deste relatório). As três sugestões foram aplicadas:

- **Normalização de `\r\n` por chunk** (`lib/sse.ts`): passou a rodar sobre o
  buffer já concatenado. Um `\r` que termina um chunk e o `\n` que abre o
  seguinte só formam par depois da junção — feita por chunk, a defesa falhava
  exatamente no caso que existe para cobrir. Teste novo com o par partido; ele
  falha contra a versão anterior (verificado).
- **`readCitations` fabricava `chunk_index: 0` e `score: 0`** (`lib/sse.ts`): os
  quatro campos passaram a ser exigidos, como já se fazia com `page_number`.
  "similaridade 0,00" na tela era número que o servidor nunca disse — e a fase
  `B.3` trava no escopo justamente não fabricar citação.
- **Trocar `conversationId` não abortava o stream** (`hooks/useChat.ts`): o
  efeito de limpeza passou a depender do `conversationId`.

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **`openChatStream` em `api.ts`** (decisão 1) é o único desvio de arquivo desta
   fase. Se o avaliador discordar, a mudança é mecânica — mover a função para
   `sse.ts` e exportar `BASE_URL` e `readErrorEnvelope` do `api.ts`.
2. **O teste da tela usa o parser mockado.** É deliberado: o parser tem oito
   testes próprios sobre bytes reais, e mockar aqui é o que permite empurrar um
   token por vez e observar a renderização incremental. Nenhum teste desta fase
   prova o caminho completo `fetch → parser → tela` — isso é o gate do compose,
   que depende da `A.4`.
3. **Recusa e `truncated` ainda não têm tratamento visual.** É escopo declarado
   da `B.4`; aqui `truncated` já é gravado na mensagem, só não é exibido.
