---
spec: 02-chat-rag
fase: B.1
slug_fase: chat-view
status: executado
tentativa: 2
reprovacoes: 1
sha_inicial: dd621eb
sha_final: 28159b6
range: dd621eb..28159b6
---

# FASE B.1 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/Yaitec-TalkDoc-chatB`, branch
> `feat/chat-rag-trackB`, criada a partir de `dev` (`dd621eb`).

## ⚠️ Dependência `A.4` ainda NÃO satisfeita — leia antes de avaliar

A `B.1` declara `Depende de: A.4` (endpoint de chat). No momento desta execução
a `A.4` **não existe**: a branch `feat/chat-rag-trackA` está em `dd621eb`, sem
nenhum commit, e não há `backend/app/api/conversations.py` no repositório.

O owner determinou execução paralela dos dois tracks. A base usada foi o
**contrato congelado da spec** — §4.3 (protocolo SSE) e §4.4 (rotas e payloads)
—, que a própria spec nomeia como fonte única (Risco 5). Consequência honesta:

- Tudo que é comportamento de cliente está implementado e **provado por teste
  offline** contra esse contrato.
- O critério de conclusão da fase que diz **"conversa criada contra o backend
  real"** está **PENDENTE**. Não foi cumprido, não foi simulado e não está
  marcado como cumprido. Ver §6.

## 1. Resumo do que foi feito

O documento que fica `ready` leva direto à conversa: a tela de chat monta sobre
o design system, cria a conversa **uma única vez** por documento (guardando o par
documento↔conversa em `localStorage`), lista as mensagens numa região viva e
oferece um campo de pergunta com `Enter` para enviar e `Shift+Enter` para quebrar
linha. O envio ainda é local — quem fala com o servidor é a `B.2`.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `frontend/src/components/ChatView.tsx` | A tela: abre/recupera a conversa, cabeçalho do documento, lista e campo |
| `frontend/src/components/MessageList.tsx` | Lista rolável com região `aria-live` e acompanhamento do fim sem sequestrar o scroll |
| `frontend/src/components/MessageInput.tsx` | Campo de pergunta controlado, com `Enter`/`Shift+Enter` e botão de envio rotulado |
| `frontend/src/components/ChatView.test.tsx` | 7 testes: criação única (inclusive sob `StrictMode`), reaproveitamento, falha, teclado |
| `frontend/src/components/MessageList.test.tsx` | 3 testes: ordem do histórico, região viva estável, distinção de quem falou |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `frontend/src/lib/types.ts` | `Citation`, `ChatRole`, `ChatMessage` e `ConversationCreated`, derivados da §4.4 |
| `frontend/src/lib/api.ts` | `createConversation()` e `listMessages()` sobre o `request()` que já existia |
| `frontend/src/App.tsx` | Troca o acompanhamento pela conversa quando o documento fica pronto; o reset esquece também a conversa |
| `frontend/src/components/ProcessingStatus.tsx` | Prop opcional `onReady` — o gancho "documento pronto" da `FEAT-0001 B.4` |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** Nenhum `fetch` novo: as duas funções de API entram no
`request()` da `FEAT-0001 B.2`, herdando `X-Session-Id`, timeout e a leitura do
envelope `{code, message}`. Nenhuma frase de erro nova: a falha ao criar a
conversa vai para `notify.error(code)`, com o mapa de `errors.ts`. Nenhuma cor
própria: `ScrollArea`, `Button`, `Skeleton` e os tokens (`bg-secondary`,
`text-muted-foreground`, `border-border`, `ring`) vêm do design system da
`FEAT-0001 B.1`. Nenhuma biblioteca nova foi instalada.

**Decisões de design:**

1. **A guarda contra conversas duplicadas é um `ref` com o `documentId`, não um
   booleano.** Um booleano continuaria "ligado" ao trocar de documento; o `ref`
   com o id responde à pergunta certa — "já pedi conversa *para este*
   documento?". O teste sob `StrictMode` cobre exatamente o caso que o duplo
   efeito do React em desenvolvimento provoca.
2. **O efeito de criação não tem bandeira de cancelamento.** Ela pareceria mais
   correta e seria um bug: no `StrictMode` o componente é desmontado e remontado
   entre a chamada e a resposta, e a bandeira descartaria a resposta da única
   conversa criada — o campo ficaria desabilitado para sempre. Atualizar estado
   de componente desmontado é inócuo no React 19. Documentado no código, porque
   é contraintuitivo.
3. **A conversa é guardada com o documento junto** (`{documentId,
   conversationId}` numa chave só). Guardar só o id da conversa faria um `F5`
   depois de trocar de PDF restaurar a conversa do documento anterior — citação
   apontando para o arquivo errado, no app cujo eixo é fundamentação.
4. **Resposta do assistente não tem balão; a pergunta tem.** O sistema visual
   declara a metáfora de papel e tinta: a resposta é o texto que se lê, a
   pergunta é a anotação na margem. Também resolve leitura — resposta longa
   dentro de balão fica pior de ler do que texto corrido.
5. **`ProcessingStatus` ganhou `onReady` em vez de o `App` consultar o
   documento por conta própria.** A alternativa (subir `useDocumentStatus` para o
   `App`) deixaria dois componentes consultando o mesmo documento a cada 1,5 s.
   **Desvio declarado:** a §5 da spec não lista `ProcessingStatus.tsx` em
   "Arquivos alterados" da `B.1`. A mudança é uma prop opcional e um efeito de
   três linhas; nenhum comportamento existente muda quando ela não é passada.
6. **Ids locais são negativos.** A mensagem otimista do usuário precisa de chave
   antes de o servidor numerar; separar as origens por sinal evita colisão com
   os `bigserial` que a `B.2`/`B.4` vão trazer.

**Desvios além do item 5:** nenhum. Nada fora do Track B foi tocado; nenhuma
fase posterior foi antecipada (o envio não fala com o servidor — isso é `B.2`).

## 5. Comandos rodados + saídas reais

```text
# lint  (make lint, parte do frontend)
$ npm run lint
> talkdoc-frontend@0.1.0 lint
> eslint src
(sem achado)

# type-check
$ npx tsc --noEmit
(sem saída — zero erro)

# testes da fase
$ npx vitest run src/components/ChatView.test.tsx src/components/MessageList.test.tsx
 Test Files  2 passed (2)
      Tests  10 passed (10)

# gate agregador do projeto, na raiz do worktree
$ make check
...
Required test coverage of 90% reached. Total coverage: 98.98%
====================== 135 passed, 6 deselected in 11.39s ======================
cd frontend && npm run test
 Test Files  8 passed (8)
      Tests  50 passed (50)

# grep de segredo nos arquivos tocados (esperado: 0)
$ grep -rniE "gemini_api_key|api[_-]?key|sk-[a-z0-9]" src/components/{ChatView,MessageList,MessageInput}.tsx src/lib/api.ts | wc -l
0
```

`make security` e `make arch` não foram rodados nesta fase: `arch` valida
imports de `backend/app/core/` e nenhum arquivo de backend foi tocado; `security`
audita dependências e nenhuma foi acrescentada. Ambos entram no gate da `B.4`,
quando o Track B estiver fechado.

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-16** (FR-15) — documento `ready` sem conversa ativa cria a conversa e
  habilita o campo. Evidência: `ChatView.test.tsx` → "cria a conversa uma única
  vez ao entrar no chat e habilita o campo", com `createConversation` chamado
  **1 vez** dentro de `<StrictMode>`; e "reaproveita a conversa guardada do mesmo
  documento, sem criar outra" (zero chamadas).
- [x] **Lista renderiza histórico na ordem** — `MessageList.test.tsx` → os três
  itens saem na ordem em que entraram.
- [x] **AC-29 (parte da `B.1`)** — `aria-live="polite"` na lista, presente desde
  o primeiro render (teste confirma que a região **não é recriada** quando a
  primeira mensagem chega); campo com `<label>` associado
  (`getByLabelText('Sua pergunta sobre o documento')`); botão de envio com
  `aria-label`; foco visível pelo `focus-within:ring` do contêiner do campo, com
  o token `--ring`.
- [x] **Envio desabilitado com entrada vazia ou em branco** — teste "não envia
  pergunta em branco": botão `disabled` e `{Enter}` com espaços não cria item.
- [x] **`Enter` envia, `Shift+Enter` quebra linha** — teste homônimo.
- [x] **Rolagem automática sem sequestrar o scroll** — implementado em
  `useStickToBottom` (o acompanhamento desliga quando a pessoa sobe mais de 48 px
  do fim). **Sem teste automatizado:** `jsdom` não faz layout, então
  `scrollHeight`/`clientHeight` são zero e qualquer asserção sobre isso provaria
  o mock, não o comportamento. Verificação visual pendente junto com o gate do
  backend real.
- [ ] **Critério de conclusão — "conversa criada contra o backend real"**:
  **PENDENTE**, `A.4` não implementada. Ver o aviso no topo.
- [x] **"layout consistente com o design system nos dois temas"** — por
  construção: toda cor usada é token semântico, que é o que troca com o tema.
  Conferência visual nos dois temas fica junto do gate acima.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (10 novos; 50 no frontend, 135 no backend)
- [x] Comandos de validação limpos (`make check` zero)
- [x] Escopo travado respeitado: nenhuma biblioteca de estado global; nenhuma cor
      fora dos tokens; conversa não é recriada a cada render (teste); textos em
      pt-BR e identificadores em inglês
- [x] Nenhum segredo/PII no diff (grep zero)
- [x] Commits em pt-BR, Conventional Commits (`28159b6`)
- [ ] Gate de backend real — **pendente da `A.4`**

## 8. (Em rework) O que mudou nesta tentativa

Rework da avaliação `FASE-B.1-chat-view-AVALIACAO.md` (tentativa 1, REPROVADO,
score 9,0). Sem BLOQUEANTE de código: o único é o gate contra o backend real,
que continua aberto (topo deste relatório). As três sugestões foram aplicadas:

- **Histórico descartado quando a pergunta chega primeiro** (`hooks/useChat.ts`):
  `mergeHistory` junta servidor e tela por `id` em vez de escolher um dos lados.
  Ids locais são negativos e nunca colidem com os do servidor.
- **Chips de sugestão clicáveis com a conversa falhada** (`components/ChatView.tsx`):
  no estado `failed` o lugar das sugestões passa a mostrar o caminho de volta
  ("recarregue a página"). Botão que não faz nada é pior que botão ausente.
- **Decisão de acompanhar o fim da lista virou função pura**
  (`components/MessageList.tsx`, `isNearBottom`): fecha a única lacuna de teste
  da fase sem inflar abstração — a regra é provável sem layout, que o jsdom não
  calcula.

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **O gate contra o backend real.** Sugestão: avaliar a fase pelo que ela
   controla (contrato, criação única, acessibilidade, escopo) e reter o gate de
   ponta a ponta para quando a `A.4` estiver em `dev` — foi assim que a `B.3` da
   `FEAT-0001` acabou reprovada por cumprir o gate contra um stub, e o caminho
   correto lá foi cumprir de verdade depois. Aqui nada foi simulado.
2. **A prop `onReady` no `ProcessingStatus`** (decisão 5) é o único arquivo fora
   da lista da §5. Se o avaliador preferir, dá para inverter e subir o
   `useDocumentStatus` para o `App` — ao custo de polling duplicado enquanto o
   documento é lido.
3. **A rolagem automática não tem teste.** Está justificado acima; se o avaliador
   quiser cobertura mesmo assim, o caminho seria extrair a decisão
   ("acompanhar ou não") para uma função pura recebendo os três números e testar
   essa função. Não fiz para não inflar a fase com abstração que só existe para o
   teste.
