---
spec: 02-chat-rag
fase: B.4
slug_fase: notices-persistence
tentativa: 1
veredito: REPROVADO
score: 8.6
threshold: 8.5
range_avaliado: 8a1e191..74afd80
---

# FASE B.4 — Avaliação independente

## 1. Veredito e score

**Veredito:** REPROVADO · **Score:** 8.6 / threshold 8.5

Reprova por **dois achados**: um BLOQUEANTE (o critério de conclusão da fase,
que exige backend real) e um IMPORTANTE que encontrei rodando o código — o
caminho de "Tentar de novo", que é a razão de existir desta fase, **duplica a
pergunta na conversa**. Reproduzi com uma sonda de teste temporária (removida ao
final; árvore limpa).

A distinção conceitual central da fase — recusa é resposta legítima, não erro —
está implementada com cuidado e é o melhor detalhe do track.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 3 | AC-19 provado (`MessageList.test.tsx:96` — recusa sem `role="alert"`, sem marca de interrompida); AC-20 provado (`ChatView.test.tsx:348` — `listMessages` com a conversa guardada e `createConversation` **não** chamado). Escopo travado: `grep -rn "alert(" src/` → 0, recusa ≠ erro, conversa não recriada. **Gate contra backend real não cumprido** (§3) e a preservação da pergunta tem defeito (§4) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | A falha vira **estado** do hook (`useChat.ts:19-22`) e a tela decide a recuperação — a inversão certa: com o aviso dentro do hook, o botão reenviaria por fora do caminho normal |
| 3 | Segurança / LGPD | 3 | 5 | Toda mensagem vem de `describeError(code)` (`useNotices.ts:56`); `ApiError.status` não é lido por nenhum componente (conferido); nenhum stack trace, nenhuma chave; grep de segredo → 0 |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Mapa de códigos **estendido**, não duplicado (`errors.ts:33-34,76-87`); canal único de avisos preservado — o `action` entrou no `useNotices`, não numa segunda via de mensagens |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `documento_nao_pronto` com severidade `info` é a leitura correta do domínio: estado transitório do documento, não falha de quem perguntou. O `useNotices` da FEAT-0001 já previa isso (`useNotices.ts:17-21`) |
| 6 | Local e nomes dos arquivos | 2 | 4 | `useNotices.ts` fora da lista da §5 — desvio declarado e correto (o botão precisa existir na camada de avisos); `App.tsx` estava na lista e não mudou, com justificativa verificável (a persistência do `documentId` já vinha da FEAT-0001 B.3) |
| 7 | Qualidade de código | 2 | 4 | Código claro e bem comentado no "porquê"; perde ponto pelo defeito de I-1, que nasce de `send()` acrescentar a mensagem otimista sem considerar que a pergunta anterior falhou e continua na lista |
| 8 | Testes e cobertura | 2 | 3 | 7 testes novos e bons; mas o teste do "Tentar de novo" (`ChatView.test.tsx:297`) assere a chamada e o campo, **não o resultado na conversa** — é exatamente a lacuna por onde I-1 passou. E `errors.test.ts:27` foi afrouxado de `toBe('error')` para "está entre as três severidades", perdendo poder de detecção |
| 9 | Migration safety | 2 | — | Não se aplica |

Média ponderada: 86/20 = 4,3 → **8.6/10**.

## 3. Achados BLOQUEANTES

### B-1. Critério de conclusão da fase não cumprido — cada código de erro e o `F5` contra o backend real

**Onde:** `SPEC_02_CHAT_RAG.md` §5, Fase B.4, *Critério de conclusão (gate)*;
`FASE-B.4-notices-persistence-EXECUCAO.md:159` marca PENDENTE.

O gate pede duas coisas: **cada** código de erro reproduzido exibindo o aviso
certo, e um `F5` no meio da conversa restaurando tudo. Nenhuma foi verificada
contra o app rodando.

E aqui a verificação real tem achado próprio esperando: auditei
`backend/app/errors.py` e o servidor **não emite o código `provedor`** em lugar
nenhum (`grep -rn "provedor" backend/app/` só encontra prosa). A §4.3 da spec o
declara no vocabulário do evento `error`, e a `B.4` corretamente o pôs no mapa —
mas hoje ele é entrada morta, e o gate "cada código de erro reproduzido" é
justamente o que revelaria isso. Não é defeito da `B.4`: é dívida da `A.4` que
o gate desta fase existe para expor.

**Correção sugerida (sem mudar código do frontend):**
1. `make up` na `dev` atual.
2. `documento_nao_pronto`: tentar entrar no chat antes de o documento ficar
   `ready` → conferir que sai como `toast.info`, não vermelho.
3. `limite_de_uso`: forçar rajada até o `429` (ou apontar a chave para uma quota
   esgotada) → conferir aviso com "Tentar de novo" e a pergunta de volta no campo.
4. `erro_interno` / `rede_indisponivel`: derrubar o backend com o front no ar.
5. `provedor`: **não é reproduzível hoje** — abrir como pendência da `A.4`
   (mapear a falha do provedor para `ProviderError(code="provedor")`) ou remover
   o código do §4.3 da spec. Decidir e registrar.
6. `F5` no meio de uma resposta em streaming → conferir que o histórico volta,
   que nenhuma conversa nova é criada, e que a resposta interrompida aparece
   marcada.
7. Registrar no EXECUCAO (tentativa 2) e reavaliar em chat zerado.

## 4. Achados IMPORTANTES

### I-1. "Tentar de novo" duplica a pergunta na conversa

**Onde:** `frontend/src/hooks/useChat.ts:104-114` (a mensagem otimista é
acrescentada em todo `send`) combinado com `frontend/src/components/ChatView.tsx:185-193`
(a ação do aviso chama `ask(failure.question)`, que passa pelo mesmo `send`).

**O que acontece:** quando o envio falha antes do primeiro token, a mensagem
otimista da pergunta **permanece** na lista (o `finally` de `useChat.ts:154-170`
só acrescenta a resposta se houve conteúdo, e nada remove a pergunta). Clicar em
"Tentar de novo" chama `send` de novo, que acrescenta **outra** mensagem
otimista com a mesma pergunta. A conversa fica com dois balões idênticos e
nenhuma resposta entre eles — no caminho que é o produto desta fase, e no erro
mais provável da demonstração (o `429`, Risco 4 da spec).

**Reproduzido** (sonda temporária, removida; árvore limpa ao final):

```text
AssertionError: expected [ …(2) ] to have a length of 1 but got 2
  ❯ __avaliacao_tmp.test.tsx:76
# a lista da conversa contém dois <li> com "qual o e-mail?" depois de
# falhar com 429 e acionar a ação "Tentar de novo" do aviso
```

**Agravante do lado do servidor:** a `A.4` persiste a pergunta **antes** de
chamar o provedor (`backend/app/chat.py`, `_prepare` → `add_message(USER, ...)`),
e o `429` de embedding/geração estoura depois disso. Então a repetição também
grava a pergunta duas vezes no banco, e as duas entram na janela de histórico do
próximo turno — o que empurra uma pergunta útil para fora de `HISTORY_WINDOW` e
distorce a condensação.

**Correção sugerida:** ao registrar a falha, remover a mensagem otimista
correspondente (o `send` a reintroduz na repetição). Concretamente, guardar o
`id` local gerado no `send` e, no ramo de falha **sem conteúdo recebido**,
descartá-lo:

```ts
// em send(), antes do run():
const optimisticId = nextLocalId.current--
// no catch/finally, quando não houve token nenhum:
if (!content) setMessages((p) => p.filter((m) => m.id !== optimisticId))
```

E acrescentar ao teste de `ChatView.test.tsx:297` a asserção que falta: depois da
repetição bem-sucedida, a conversa tem **uma** pergunta e **uma** resposta.

## 5. Sugestões

- **`errors.test.ts:27` ficou fraco demais.** Trocar `toBe('error')` por
  "está entre as três severidades" foi a reação certa a uma regra que virou
  falsa, mas o resultado aceita qualquer coisa — um código marcado `success` por
  engano passaria. O teste que segura a intenção é uma tabela explícita:
  `expect(describeError('documento_nao_pronto').severity).toBe('info')` e
  `expect(describeError('limite_de_uso').severity).toBe('error')`. A verificação
  de canal em `ChatView.test.tsx:181` cobre um caso; a tabela cobre todos.
- **Chips de pergunta sugerida ficam clicáveis quando a conversa falhou**
  (`ChatView.tsx:203-214` renderiza o `emptyState` também no estado `failed`; o
  clique morre no `return` de `useChat.ts:95`). Botão que não faz nada é pior que
  botão ausente — desabilitar junto com o campo.
- **A restauração descarta o histórico se a pessoa perguntar antes de ele
  chegar** (`useChat.ts:67-68`). O guard evita apagar a pergunta em voo, mas o
  preço é perder a conversa anterior pelo resto da sessão. Mesclar por `id`
  resolve os dois.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ §5 estruturalmente válida
EXIT=0

$ git merge-base --is-ancestor 74afd80 HEAD && echo ANCESTOR-OK
ANCESTOR-OK      # idem 8a1e191

$ make check
cd backend && uv run ruff check .
cd frontend && npm run lint
cd backend && uv run mypy app
cd frontend && npx tsc --noEmit
cd backend && uv run lint-imports --config .importlinter
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

# escopo travado da B.4
$ grep -rn "alert(" frontend/src | wc -l                            → 0
$ grep -rniE "gemini_api_key|sk-[a-z0-9]{10}" frontend/src | wc -l  → 0

# o código `provedor` não existe no servidor
$ grep -rn "provedor" backend/app/ | grep -c 'code = '              → 0
$ grep -n 'code = ' backend/app/errors.py
    code = "erro_interno" | "arquivo_grande" | "arquivo_invalido" | "nao_encontrado"
         | "limite_de_uso" | "documento_nao_pronto" | "pdf_muitas_paginas"
         | "pdf_texto_longo" | "pdf_sem_texto"
# → `provedor` (§4.3 da spec) não é emitido por ninguém

# sonda do avaliador para I-1 (arquivo temporário, removido em seguida)
$ npx vitest run src/components/__avaliacao_tmp.test.tsx
 FAIL  quantas bolhas de pergunta sobram depois de falhar e repetir
 AssertionError: expected [ …(2) ] to have a length of 1 but got 2
$ rm -f src/components/__avaliacao_tmp.test.tsx

# contraste dos pares novos desta fase
LIGHT warning sobre background   5.40:1   ✅ AA ("Resposta interrompida antes do fim.")
DARK  warning sobre background  10.11:1   ✅ AA
LIGHT muted-foreground sobre bg  7.13:1   ✅ AA ("sem base no documento")
DARK  muted-foreground sobre bg  7.71:1   ✅ AA

$ git status --short
(vazio — árvore limpa ao final)
```

## 7. Itens da fase / DoD não atendidos

- **Gate da §5:** "cada código de erro reproduzido exibe o aviso certo" — não
  cumprido (B-1); e `provedor` não é reproduzível, porque o servidor não o emite.
- **Gate da §5:** "um `F5` no meio da conversa restaura tudo" — provado a partir
  da conversa guardada em teste, não contra o backend real (B-1).
- **Escopo travado "não perder a pergunta quando o envio falha":** cumprido na
  letra (a pergunta volta ao campo) mas o caminho de recuperação tem o defeito
  I-1.
- **DoD §9 da spec:** "`B.4 notices-persistence` — avisos acionáveis, recusa
  distinta de erro, `F5` restaura tudo" ⏳.
- **Elegibilidade (§2.11.4):** depende da `B.3`, não concluída.

## 8. Divergências entre o relatório e o código real

- **Uma divergência de fato, no EXECUCAO §6:** o item "devolve a pergunta ao
  campo e oferece repetir quando o envio falha" está marcado `[x]` com a
  evidência "acionar a ação reenvia **a mesma pergunta** e o campo volta a ficar
  limpo". As duas afirmações são verdadeiras, mas o item declara cumprida uma
  propriedade da fase — a recuperação da falha — que na tela produz a conversa
  duplicada de I-1. O relatório não mente; o teste que o sustenta é que olha
  para o lugar errado.
- **Verificadas e confirmadas:** recusa inferida de `citations` vazio só em
  resposta completa (`MessageList.tsx:111-113`) — e confere com o servidor, que
  emite `token(REFUSAL_MESSAGE) → citations:[] → done` em `chat.py::_refuse`;
  `App.tsx` de fato não precisava mudar; `useNotices.ts` é o único arquivo fora
  da lista; nenhum componente lê `ApiError.status`.
- **A auditoria de acessibilidade do EXECUCAO §9.4 confere**, e eu fechei a parte
  que ela declarou em aberto: todos os pares de cor tocados pelo track passam AA
  (medições na §6 desta avaliação e na da `B.3`).
