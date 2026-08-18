---
spec: 02-chat-rag
fase: B.4
slug_fase: notices-persistence
status: executado
tentativa: 2
reprovacoes: 1
sha_inicial: 8a1e191
sha_final: 74afd80
range: 8a1e191..74afd80
---

# FASE B.4 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/Yaitec-TalkDoc-chatB`, branch
> `feat/chat-rag-trackB`.

## ✅ Gate executado na tentativa 2 (o aviso abaixo é da tentativa 1)

Os seis códigos de erro do mapa foram reproduzidos contra o servidor real —
inclusive `provedor`, que a avaliação supunha inexistente — e o `F5` no meio da
conversa **e no meio do stream** restaurou tudo. Evidências em §10.

## ⚠️ (Tentativa 1) Gate com o backend real ainda PENDENTE

"Cada código de erro reproduzido exibe o aviso certo; um `F5` no meio da conversa
restaura tudo" só pode ser conferido de ponta a ponta com a `A.4` no ar. O que
está provado offline: o aviso certo por código (inclusive o canal, que muda com
a severidade), a pergunta preservada, a recusa distinta de erro e a restauração
do histórico a partir da conversa guardada.

## 1. Resumo do que foi feito

Erro técnico agora devolve a pergunta ao campo e traz, no próprio aviso, o botão
que refaz o envio. A recusa por falta de fundamento aparece como resposta do
assistente, com marca sutil ("sem base no documento") e sem nenhum sinal de
falha; resposta interrompida tem marca própria, separada da recusa. Ao recarregar
a página, a conversa guardada traz o histórico do servidor — sem abrir conversa
nova. A conversa vazia parte de três perguntas sugeridas.

## 2. Arquivos CRIADOS

Nenhum, como a §5 previa.

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `frontend/src/lib/errors.ts` | +`provedor` e +`documento_nao_pronto` no mapa por código |
| `frontend/src/hooks/useNotices.ts` | Aviso aceita ação de recuperação (`{label, onClick}`) |
| `frontend/src/hooks/useChat.ts` | Falha vira estado reportado (`ChatFailure`), não aviso direto; carrega o histórico da conversa |
| `frontend/src/components/ChatView.tsx` | Repõe a pergunta que falhou, dispara o aviso com "Tentar de novo", estado inicial com sugestões |
| `frontend/src/components/MessageList.tsx` | Recusa e `truncated` com marcação própria; rótulo da lista; estado vazio |
| `frontend/src/components/ChatView.test.tsx` | +4 testes (repetir, recusa, restauração, sugestão) |
| `frontend/src/components/MessageList.test.tsx` | +3 testes (recusa, interrompida, estado inicial) |
| `frontend/src/lib/errors.test.ts` | Severidade deixa de ser sempre `error` — ver decisão 2 |

`App.tsx` estava na lista da §5 e **não** precisou mudar: a persistência do
`documentId` e a restauração no boot já existiam da `FEAT-0001 B.3`, e a da
conversa entrou na `B.1`. Alterá-lo só para constar seria diff sem função.

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** O mapa de códigos foi **estendido**, não duplicado: os dois
códigos novos entraram em `errors.ts`, e todo aviso continua saindo por
`notify.error(code)`. Nenhum componente escreve frase de erro própria. `Button`,
`Skeleton` e os tokens vêm do design system. Nenhuma dependência nova.

**Decisões de design:**

1. **A falha virou estado do hook (`ChatFailure`), não um aviso disparado lá
   dentro.** Quem sabe oferecer o caminho de volta — repor a pergunta no campo e
   refazer o envio pelo mesmo caminho do envio normal — é a tela. Com o aviso
   dentro do hook, o botão "Tentar de novo" reenviaria por fora e o campo ficaria
   com texto velho depois de a repetição dar certo.
2. **`documento_nao_pronto` tem severidade `info`, não `error`.** É estado
   transitório do documento, não falha de quem perguntou. Isso **quebrou um teste
   existente** (`errors.test.ts` assertia `severity === 'error'` para todo
   código), e a asserção foi trocada por "a severidade é uma das que o despacho
   conhece". A regra antiga tinha virado falsa: o `useNotices` da `FEAT-0001` foi
   escrito justamente para que um código não-erro saísse por outro canal, com
   comentário dizendo isso. O teste da tela agora **verifica o canal**: sai por
   `toast.info` e não por `toast.error`.
3. **A recusa é inferida de `citations` vazio, e só em resposta completa.** É o
   sinal que o contrato dá (FR-6: sem chunk acima do limiar, recusa com citações
   vazias). Resposta **interrompida** fica de fora da inferência de propósito:
   ela pode estar sem citação só porque o stream caiu antes do evento
   `citations`, e chamar isso de recusa seria inventar significado. As duas
   marcas são visualmente distintas e nenhuma delas usa a cor destrutiva.
4. **Perguntas sugeridas genéricas.** O cliente não lê o conteúdo do PDF; sugerir
   algo específico ("quais serviços a empresa oferece?") para um documento que
   não fala de empresa nenhuma ensinaria a desconfiar da sugestão na primeira
   interação.
5. **O histórico é carregado pelo `useChat`, não pelo `ChatView`.** As mensagens
   são estado do hook; carregar fora dele exigiria uma via de escrita só para
   isso. A carga só substitui a lista se ela ainda estiver vazia — uma pergunta
   feita antes de a resposta do histórico chegar não pode ser apagada por ela.
6. **`ResizeObserver` dublê nos testes.** O `ScrollArea` do Radix o usa e o jsdom
   não o implementa; o dublê existe por causa do ambiente de teste, não por
   causa do produto. Documentado nos dois arquivos onde aparece.

**Desvio declarado:** `useNotices.ts` não está na lista de "Arquivos alterados"
da `B.4`. A fase pede aviso **com botão de repetir**, e o botão precisa existir na
camada de avisos — a alternativa seria um segundo lugar de onde mensagens saem,
exatamente o que o `useNotices` foi criado para impedir.

## 5. Comandos rodados + saídas reais

```text
# suíte inteira do frontend
$ npx vitest run
 Test Files  10 passed (10)
      Tests  75 passed (75)

# gate agregador
$ make check
...
====================== 135 passed, 6 deselected ======================
cd frontend && npm run test
 Test Files  10 passed (10)
      Tests  75 passed (75)

# segurança
$ make security
cd backend && uv run bandit -q -r app
cd backend && uv run pip-audit
No known vulnerabilities found
cd frontend && npm audit --audit-level=high
found 0 vulnerabilities
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-12, lado do cliente** (FR-11) — "devolve a pergunta ao campo e oferece
  repetir quando o envio falha": `429`/`limite_de_uso` vira aviso com
  `action.label === 'Tentar de novo'`; acionar a ação reenvia **a mesma
  pergunta** (`openChatStream` chamado com ela) e o campo volta a ficar limpo.
- [x] **AC-19** (FR-18) — "exibe a recusa como resposta do assistente, sem aviso
  de erro": resposta sem citações mostra "sem base no documento", nenhum
  `toast.error` é disparado, nenhuma área de citação é desenhada. Em
  `MessageList.test.tsx`, a recusa não tem `role="alert"` nem marca de
  interrompida.
- [x] **AC-20** (FR-19) — "restaura o histórico da conversa guardada, sem criar
  outra": com o par documento↔conversa no `localStorage`, `listMessages` é
  chamado com `conv-guardada`, as duas mensagens e a citação aparecem, e
  `createConversation` **não** é chamado.
- [x] **Queda no meio do stream preserva o texto e marca a mensagem** — teste
  "marca a resposta interrompida sem confundi-la com recusa" e, na `B.2`, "trata
  erro no meio do stream preservando o texto recebido".
- [x] **Estado vazio com perguntas sugeridas** — "parte de uma pergunta sugerida
  quando a conversa está vazia": o clique envia a pergunta; o estado inicial some
  quando a primeira mensagem entra.
- [x] **Nunca exibir stack trace, código de exceção ou chave** — o que a tela
  mostra vem sempre de `describeError(code)`. `ApiError.status` existe só para
  diagnóstico: nenhum componente o lê (os `.status` que aparecem em
  `frontend/src/components/` são todos de estado de documento, envio ou
  conversa, conferidos um a um).
- [x] **Não usar `alert()`** — `grep -rn "alert(" frontend/src` → 0.
- [x] **Critério de conclusão contra o backend real**: cumprido na tentativa 2
  (§10) — cada código reproduzido com o aviso certo no canal certo, e o `F5`
  restaurando a conversa sem criar outra, com a resposta interrompida marcada.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (7 novos; 75 no frontend)
- [x] `make check` zero; `make security` sem achado alto
- [x] Escopo travado respeitado: recusa não é tratada como erro; a pergunta não
      se perde; conversa não é recriada ao restaurar; sem `alert()`
- [x] Nenhum segredo/PII no diff
- [x] Commits em pt-BR, Conventional Commits (`74afd80`)
- [x] Gate contra o backend real — cumprido na tentativa 2 (§10)

## 8. (Em rework) O que mudou nesta tentativa

Rework da avaliação `FASE-B.4-notices-persistence-AVALIACAO.md` (tentativa 1,
REPROVADO, score 8,6). O BLOQUEANTE é o gate contra o backend real e continua
aberto (topo deste relatório). O que mudou no código:

### I-1 — "Tentar de novo" duplicava a pergunta na conversa

Confirmado: o `send` acrescentava uma mensagem otimista em todo envio, e a
mensagem da tentativa que falhou permanecia na lista. Acionar a ação do aviso
deixava dois balões idênticos, sem resposta entre eles.

**Cliente** (`hooks/useChat.ts`): o `send` guarda o id local que gerou, e o
`finally` o descarta quando o turno terminou **em falha e sem nenhum token**.
Cancelamento não entra nesse ramo — desistir é decisão de quem perguntou, e a
pergunta continua tendo acontecido. A pergunta já voltava para o campo; agora a
conversa também não guarda balão órfão.

**Servidor** (`app/chat.py`, dívida da `A.4` que o mesmo defeito expunha): a
pergunta é persistida antes da chamada ao provedor (FR-9), então a repetição a
gravava duas vezes e as duas entravam na janela de histórico do turno seguinte.
`_is_retry` reconhece a repetição pelo único jeito de a conversa terminar numa
mensagem do usuário — turno anterior morto entre persistir a pergunta e produzir
texto — e reaproveita a linha existente em vez de criar outra.

**Testes:** a asserção que faltava está no teste do "Tentar de novo"
(`ChatView.test.tsx`): depois da repetição bem-sucedida, a conversa tem **uma**
pergunta e **uma** resposta. Entraram também o contraponto do cancelamento
(a pergunta permanece) e, no backend, `test_repetir_a_pergunta_que_falhou_nao_a_grava_duas_vezes`
com o seu contrapeso para pergunta diferente. Os três falham contra o código
anterior — verificado revertendo a correção antes de fixá-la.

### Sugestões da avaliação, todas aplicadas

- **`errors.test.ts` afrouxado:** a asserção "está entre as três severidades"
  virou tabela explícita código→severidade, mais a checagem de que a tabela cobre
  `ERROR_CODES` inteiro — código novo sem severidade declarada reprova em vez de
  entrar sem ninguém decidir como ele aparece.
- **Chips clicáveis com a conversa falhada:** o estado vazio passa a mostrar o
  caminho de volta ("recarregue a página") no lugar das sugestões quando a
  conversa não abriu, em vez de botões cujo clique morria calado.
- **Restauração descartava o histórico:** `mergeHistory` junta os dois lados por
  `id` (os locais são negativos e nunca colidem), então perguntar antes de o
  histórico chegar deixou de custar a conversa anterior.

### O código `provedor` da §4.3 **é** emitido pelo servidor

A avaliação abriu como pendência da `A.4` ("entrada morta no mapa") a partir de
um `grep` em `backend/app/errors.py`. O código existe fora desse arquivo:
`ChatProviderError` em `app/adapters/gemini.py:103` (`code = "provedor"`,
`status_code = 502`), levantada por `_fail_chat` em toda falha do provedor de
chat que não seja quota. Já havia teste cobrindo a rota inteira —
`test_falha_do_provedor_na_abertura_do_stream_nao_vira_mensagem_vazia` assere
`502` e `{"code": "provedor"}`. Nada a implementar e nada a remover da spec; o
que falta é só reproduzir o código no gate, e ele é reproduzível.

### Estado da suíte depois do rework

`make check` verde: 250 testes no backend (eram 248; +2 do `_is_retry`),
cobertura de `core/` em 99,55%, e 84 no frontend (eram 75; +9 entre a asserção
que faltava, o contrapeso do cancelamento, a mescla do histórico, o estado vazio
da conversa falhada, `isNearBottom` e os dois do parser). `make security` sem
achado. Os quatro gates da §5 do track continuam pendentes e fecham na mesma
passada contra o `docker compose`, com a `A.4` já na `dev`.

## 9. Itens em aberto / dúvidas para o avaliador

1. **Um teste existente foi alterado** (`errors.test.ts`, decisão 2). Não foi para
   fazer código passar: a asserção "todo código é `error`" deixou de ser
   verdadeira quando entrou um código legitimamente informativo, e a cobertura do
   comportamento **aumentou** (o teste da tela agora verifica o canal do aviso).
   Vale um olhar de fora.
2. **A recusa é inferida, não declarada pelo servidor.** Se a `A.4` puder marcar a
   recusa no evento `done` (por exemplo `refused: true`), o cliente troca a
   inferência por leitura direta e some com a única heurística do frontend. Como
   o contrato da §4.3 não tem esse campo, não o inventei.
3. **`useNotices.ts` fora da lista de arquivos** (desvio declarado acima).
4. **Auditoria de acessibilidade** feita sobre a tela inteira do chat: campo
   rotulado; lista da conversa com nome e `aria-live="polite"`; resposta em
   construção muda para o leitor de tela, com "pensando" anunciado uma vez por
   `role="status"`; chips alcançáveis por `Tab` com nome descritivo; diálogo com
   foco e `Esc` do Radix; recusa e interrupção sinalizadas por **ícone + texto**,
   nunca só por cor; foco visível em todo controle (o campo mostra o anel no
   contêiner, já que o `textarea` tem `outline-none`). Não há teste automatizado
   de contraste — os pares usados são os tokens auditados na `FEAT-0001 B.1`.

## 10. Gate contra o backend real (tentativa 2, 2026-08-17)

Ambiente: `docker compose` da `dev` com a `A.4` mergeada, `Exemplo-YAITEC.pdf`
ingerido pela API do compose (3 páginas, 10 chunks, `status: ready`), navegador
dirigido por Playwright contra `http://localhost:5173` (o nginx do frontend, não
o dev server). Chave real do Gemini; nenhum dublê em nenhum ponto do caminho.

### Cada código de erro, reproduzido de verdade

| Código | Como foi provocado | Resposta do servidor | O que a tela mostrou |
|---|---|---|---|
| `nao_encontrado` | pergunta em conversa inexistente | `404 {"code":"nao_encontrado"}` | — (verificado na API) |
| `arquivo_invalido` | upload de arquivo que não é PDF | `422 {"code":"arquivo_invalido"}` | — (verificado na API) |
| `documento_nao_pronto` | conversa aberta antes de o PDF ficar `ready` | `409 {"code":"documento_nao_pronto"}` | aviso **info**, não vermelho |
| `limite_de_uso` | rajada até a quota real do free tier | `429 {"code":"limite_de_uso"}` (7 de 18) | aviso com "Tentar de novo" |
| `erro_interno` | banco derrubado no meio da requisição | `500 {"code":"erro_interno"}` | "Algo deu errado no servidor" |
| `provedor` | `GEMINI_CHAT_MODEL` apontado para modelo inexistente | `502 {"code":"provedor"}` | "O provedor de IA falhou" |
| `rede_indisponivel` | backend **e** frontend fora do ar com a página aberta | falha de rede no `fetch` | "Sem resposta do servidor" |

O `provedor` era o item que a avaliação dava como irreproduzível. Ele existe,
sai com `502` e o log registra `chat.provider_failed` + `chat.error phase=pre_stream`:

```text
{"reason": "404 NOT_FOUND … models/gemini-modelo-inexistente is not found …",
 "status": 404, "code": "provedor", "event": "chat.provider_failed"}
```

Nota de rota: com o nginx no ar e só o backend fora, o cliente recebe o `502` do
proxy e o aviso certo é `erro_interno`. `rede_indisponivel` é o caso em que o
`fetch` não chega a lugar nenhum — reproduzido derrubando os dois contêineres.

### `F5` restaura tudo

```text
F5 sobre a conversa guardada: 2 mensagens restauradas | POST /api/conversations: 0 | chips: 5
F5 no meio do stream:         4 mensagens             | conversas novas: 0 | 'Resposta interrompida': 1
```

### I-1 fechado ponta a ponta

```text
envio falhou → 0 balões na conversa, pergunta de volta no campo: True
após 'Tentar de novo': 2 balões (1 pergunta + 1 resposta) | 5 chips
no banco: #59 user 'quais são os valores da YAITEC?' | #60 assistant (5 citações)
→ cópias da pergunta no histórico: 1
```

A falha some da conversa e volta para o campo; a repetição produz **uma**
pergunta e **uma** resposta, na tela e no banco — que é o que o defeito I-1
quebrava dos dois lados.

### Achado novo para a `A.4` (fora do escopo desta fase)

Na rajada de 18 perguntas simultâneas, 8 responderam `500 erro_interno` com
`RuntimeError: Cannot send a request, as the client has been closed` vindo do
SDK do Gemini. A criação preguiçosa do `Client` em `GeminiEmbeddingClient._models()`
não é protegida contra concorrência: no primeiro uso simultâneo depois de subir
o processo, várias threads criam clientes, o descartado é finalizado e fecha o
transporte que as outras estavam usando. É transitório (o cliente vencedor
sobrevive) e não afeta um usuário sozinho, mas duas abas na primeira pergunta
bastam. Correção sugerida: criar o cliente no `lifespan`, ou proteger a criação
preguiçosa com um `threading.Lock`.

**Capturas:** `gate-b/06-f5-no-meio-do-stream.png`, `gate-b/10-rede-indisponivel.png`, `gate-b/12-provedor-na-ui.png`, `gate-b/13-tentar-de-novo-ok.png`.

> **Versão exercitada:** a imagem do compose foi construída em `e76fbed`.
> Entre ele e o HEAD desta branch o único delta em código de aplicação é a
> tipagem de `chat_timeout_seconds`/`condense_timeout_seconds` (int → float,
> vinda do rework paralelo da `A.4`), que não toca nada medido aqui. O
> backend foi reconstruído no HEAD ao final e voltou a responder `/api/health`,
> `POST /api/conversations` (201) e `GET .../messages` (200).
