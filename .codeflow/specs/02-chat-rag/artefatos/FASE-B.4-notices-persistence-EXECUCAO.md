---
spec: 02-chat-rag
fase: B.4
slug_fase: notices-persistence
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: 8a1e191
sha_final: 74afd80
range: 8a1e191..74afd80
---

# FASE B.4 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/Yaitec-TalkDoc-chatB`, branch
> `feat/chat-rag-trackB`.

## ⚠️ Gate com o backend real ainda PENDENTE

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
  mostra vem sempre de `describeError(code)`; `ApiError.status` existe só para
  diagnóstico e não é renderizado em lugar nenhum (grep por `\.status` nos
  componentes: nenhum uso).
- [x] **Não usar `alert()`** — `grep -rn "alert(" frontend/src` → 0.
- [ ] **Critério de conclusão contra o backend real**: **PENDENTE**, `A.4`.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (7 novos; 75 no frontend)
- [x] `make check` zero; `make security` sem achado alto
- [x] Escopo travado respeitado: recusa não é tratada como erro; a pergunta não
      se perde; conversa não é recriada ao restaurar; sem `alert()`
- [x] Nenhum segredo/PII no diff
- [x] Commits em pt-BR, Conventional Commits (`74afd80`)
- [ ] Gate contra o backend real — **pendente da `A.4`**

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

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
