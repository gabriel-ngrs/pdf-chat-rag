---
id: FEAT-0003
slug: biblioteca-documentos
title: "Biblioteca de documentos: múltiplos PDFs, troca de documento e conversas persistidas"
type: feature
status: draft
priority: P2
size: M
wave: multi
domain: fullstack
bounded_context: library
cross_context: [ingestion, rag]
created_at: 2026-08-17
updated_at: 2026-08-17
owner: gabriel
depends_on: [FEAT-0001, FEAT-0002]
blocks: []
quality_gate:
  scorer: phase-evaluator
  threshold: 8.5
---

# FEAT-0003 — Biblioteca de documentos

> **Nota de planning (2026-08-17):** spec **opcional (P2)**. É o escopo que vai além do que o desafio exige. **Nada em `FEAT-0001` ou `FEAT-0002` depende dela** — se o prazo apertar, as duas primeiras specs entregam o desafio completo e esta fica documentada como próximo passo no README, o que lê como planejamento e não como corte.
>
> A modelagem que a torna barata já foi feita: `documents.session_id` existe desde `FEAT-0001` e `conversations.document_id`/`conversations.session_id` desde `FEAT-0002`. Por isso esta spec é **incremento, não refatoração** — quase tudo aqui é leitura e interface sobre dados que já estão persistidos.
>
> **Fora do escopo desta spec:** busca cross-documento (decidida contra em `FEAT-0002` §8, OQ-2); autenticação e contas reais; compartilhamento entre sessões; renomear documento; exportar conversa; paginação da biblioteca.

## Resumo executivo (TL;DR)

| | |
|---|---|
| **O quê** | A pessoa mantém vários PDFs, troca entre eles, e reencontra as conversas anteriores de cada documento ao voltar depois. |
| **Por quê** | Um app que esquece tudo a cada recarga parece protótipo. Persistência e biblioteca são o que transformam a demo em produto — e o dado já está no banco. |
| **Backend-Infra** | Listagem de documentos da sessão, exclusão com cascade, listagem e retomada de conversas por documento. |
| **Frontend** | Barra lateral com a biblioteca e o estado de cada documento, seleção do documento ativo, lista de conversas e exclusão com confirmação. |
| **Decisão** | Escopo continua por documento: a conversa pertence a um PDF. A biblioteca organiza, não mistura fontes. |
| **Tamanho** | M — 3 fases no Track A (backend) e 3 no Track B (frontend). |

## Sumário

1. Problema e contexto
2. Requisitos
3. Critérios de aceite
4. Abordagem técnica
5. Plano de desenvolvimento por fases
6. Riscos
7. Rollout
8. Open Questions
9. Definition of Done (gate por etapa)

## 1. Problema e contexto

Depois de `FEAT-0001` e `FEAT-0002`, o app faz o que o desafio pede: sobe um PDF e conversa com ele. Mas o que já está no banco é maior do que o que a interface mostra — `documents` guarda todos os documentos que a sessão enviou, e `conversations` guarda todas as conversas, com `session_id` e `document_id` em ambas. Hoje nada disso é navegável: ao recarregar a página, a pessoa perde o acesso ao que já processou, mesmo com os dados intactos e os embeddings pagos.

Esta spec expõe o que já existe. É a razão de o custo ser baixo: não há schema novo (fora de um índice), não há embedding novo, não há chamada a mais ao provedor. É leitura, roteamento e interface.

O seam central é a **identidade de sessão** decidida em `FEAT-0001`: o UUID em `localStorage` enviado no header `X-Session-Id`. Ele é estável entre recargas do browser, e é ele que torna "minhas conversas anteriores" um conceito bem definido sem autenticação.

Uma consequência precisa ser explícita, porque envolve dado do usuário: **o isolamento entre sessões é organizacional, não uma fronteira de segurança**. Quem conhecer um `session_id` alheio acessa aqueles documentos. Isso é aceitável num desafio sem autenticação, mas é registrado aqui e no README como limitação conhecida — não como algo que passou despercebido.

### 1.1 Princípios invioláveis

1. **`backend/app/core/` não importa `fastapi`, `asyncpg` nem `google.genai`.** Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`.
2. **Retrieval continua filtrado por `document_id`.** Origem: `.codeflow/constitution.md` (citação estruturada e fundamentação) + decisão OQ-2 em `FEAT-0002` §8. Ter biblioteca **não** habilita busca cross-documento.
3. **Toda entrada externa é validada no servidor.** Origem: rule universal `security`, `## Regras`.
4. **SQL parametrizado; nunca concatenação com input externo.** Origem: rule universal `security`, `## Anti-regras`.
5. **Toda consulta que retorna dado de usuário filtra por `session_id` no servidor** — nunca confiando em filtro feito no cliente. Origem: rule universal `security` (`## Anti-regras`, "Não confiar em validação só do lado do cliente").
6. **Identificadores em inglês; mensagens ao usuário em pt-BR.** Origem: rule universal `naming`, `## Regras`.
7. **Todo código novo tem teste; teste é determinístico.** Origem: rule universal `testing`, `## Regras`.
8. **`mypy --strict` e `tsc` strict zerados.** Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`.
9. **Diff mínimo: nada de refatorar `FEAT-0001`/`FEAT-0002` de passagem.** Origem: rule universal `code-quality` (`## Regras`, "Diff mínimo") e constitution universal (`## Princípios invariantes`).

## 2. Requisitos

### Funcionais

- **FR-1** — `GET /api/documents` lista os documentos da sessão (header `X-Session-Id`), com id, nome, estado, contagem de páginas e data, ordenados do mais recente para o mais antigo.
- **FR-2** — `DELETE /api/documents/{id}` remove o documento da sessão junto de seus chunks, conversas e mensagens, em cascade. Documento de outra sessão responde `404`, não `403` — não confirmar existência.
- **FR-3** — `GET /api/documents/{id}/conversations` lista as conversas daquele documento na sessão, com data e um resumo derivado da primeira pergunta.
- **FR-4** — `GET /api/conversations/{id}/messages` (já existente em `FEAT-0002`) permite retomar uma conversa anterior com o histórico completo e as citações.
- **FR-5** — Toda rota desta spec filtra por `session_id` no servidor; nenhuma delas aceita `session_id` vindo do corpo ou da query string.
- **FR-6** — A UI exibe uma barra lateral com a biblioteca de documentos, indicando o estado de cada um e destacando o ativo.
- **FR-7** — Selecionar um documento na barra lateral troca o contexto do chat para ele, carregando suas conversas.
- **FR-8** — A UI lista as conversas do documento ativo e permite retomar qualquer uma, restaurando o histórico.
- **FR-9** — A UI permite iniciar uma conversa nova sobre o documento ativo, sem apagar as anteriores.
- **FR-10** — A UI permite excluir um documento, com confirmação explícita que avisa que as conversas dele serão perdidas.
- **FR-11** — Com a biblioteca vazia, a UI mostra um estado inicial que conduz ao upload.
- **FR-12** — Documento em `processing` aparece na biblioteca com seu progresso e não é selecionável para conversa.

### Não-funcionais

- **NFR-1** — Listar a biblioteca e as conversas não gera nenhuma chamada ao provedor de IA — é leitura de banco.
- **NFR-2** — As consultas de listagem usam índice por `session_id` e por `document_id`; nenhuma varre a tabela inteira.
- **NFR-3** — A exclusão é atômica: ou tudo é removido, ou nada.
- **NFR-4** — `make lint`, `make typecheck` e `make test` retornam zero; a suíte roda offline.
- **NFR-5** — O isolamento por sessão está documentado no README como limitação conhecida, não como garantia de segurança.
- **NFR-6** — Nenhuma alteração de `FEAT-0001`/`FEAT-0002` além do estritamente necessário para expor os dados.

## 3. Critérios de aceite

- **AC-1** (FR-1) — *Dado* que enviei três PDFs nesta sessão, *quando* chamo `GET /api/documents`, *então* recebo os três, do mais recente para o mais antigo, com estado e contagem de páginas.
- **AC-2** (FR-1, FR-5) — *Dado* dois `X-Session-Id` distintos com documentos próprios, *quando* listo com um deles, *então* recebo apenas os documentos daquela sessão.
- **AC-3** (FR-2) — *Dado* um documento com chunks e duas conversas, *quando* faço `DELETE`, *então* documento, chunks, conversas e mensagens somem, e a listagem deixa de retorná-lo.
- **AC-4** (FR-2) — *Dado* um documento de outra sessão, *quando* tento excluí-lo, *então* recebo `404` e o documento permanece intacto.
- **AC-5** (NFR-3) — *Dado* que a exclusão falha no meio, *quando* a transação é revertida, *então* nem o documento nem suas conversas ficam parcialmente removidos.
- **AC-6** (FR-3) — *Dado* um documento com duas conversas, *quando* chamo `GET /api/documents/{id}/conversations`, *então* recebo as duas com data e um resumo derivado da primeira pergunta de cada.
- **AC-7** (FR-3, FR-5) — *Dado* um documento de outra sessão, *quando* listo suas conversas, *então* recebo `404`.
- **AC-8** (FR-4) — *Dado* uma conversa antiga com três trocas, *quando* a retomo, *então* vejo as seis mensagens na ordem original, com as citações preservadas.
- **AC-9** (FR-6, FR-12) — *Dado* documentos em estados diferentes, *quando* abro a biblioteca, *então* cada um mostra seu estado, o que está em `processing` exibe progresso e não é selecionável.
- **AC-10** (FR-7) — *Dado* dois documentos prontos, *quando* seleciono o segundo, *então* o chat passa a operar sobre ele e as conversas listadas são as dele.
- **AC-11** (FR-8, FR-9) — *Dado* um documento com conversas anteriores, *quando* clico em "nova conversa", *então* começo do zero sem perder as anteriores, que continuam listadas.
- **AC-12** (FR-10) — *Dado* que clico em excluir, *quando* a confirmação aparece, *então* ela avisa que as conversas serão perdidas, e só após confirmar o documento some da barra lateral.
- **AC-13** (FR-11) — *Dado* uma sessão sem documentos, *quando* abro o app, *então* vejo um estado inicial em pt-BR que conduz ao upload.
- **AC-14** (NFR-1) — *Dado* que listo biblioteca e conversas repetidamente, *quando* inspeciono as chamadas ao provedor, *então* nenhuma foi feita.
- **AC-15** (NFR-4) — *Dado* nenhuma `GEMINI_API_KEY` no ambiente, *quando* rodo `make test`, *então* a suíte passa inteira.

## 4. Abordagem técnica

### Mapa NOVO vs. REUSADO vs. REMOVIDO

**REUSADO** (existe após `FEAT-0001` e `FEAT-0002`; consumido ou estendido, nunca duplicado):

| Caminho | Como é reusado |
|---|---|
| `db/001_init.sql` | `documents.session_id` já existe — nenhuma coluna nova é necessária. |
| `db/002_conversations.sql` | `conversations.document_id` e `.session_id` já existem. |
| `backend/app/adapters/repository.py` | Ganha os métodos de listagem e exclusão, no mesmo padrão de SQL parametrizado. |
| `backend/app/api/documents.py` | Ganha as rotas de listagem e exclusão. |
| `backend/app/api/conversations.py` | Ganha a listagem de conversas por documento; `GET /messages` é consumido como está (FR-4). |
| `backend/app/api/schemas.py` | Ganha os schemas de listagem. |
| `backend/tests/conftest.py`, `fakes.py` | Fixtures e fakes consumidos como estão. |
| `frontend/src/lib/api.ts` | Ganha os métodos de biblioteca; o header `X-Session-Id` já é enviado. |
| `frontend/src/lib/types.ts` | Ganha os tipos de listagem. |
| `frontend/src/App.tsx` | Alterado para acomodar a barra lateral e o documento ativo. |
| `frontend/src/components/ChatView.tsx` | Alterado para receber o documento e a conversa ativos por prop. |
| `frontend/src/components/ProcessingStatus.tsx` | Reusado dentro do item da biblioteca para o documento em `processing`. |

**NOVO:**

- `db/003_library_indexes.sql` — índices por `session_id` e por `(document_id, created_at)`, e as `FOREIGN KEY ... ON DELETE CASCADE` se ainda não declaradas.
- `backend/tests/test_library_api.py` — isolamento por sessão, cascade e atomicidade.
- `frontend/src/components/LibrarySidebar.tsx`, `DocumentItem.tsx`, `ConversationList.tsx`, `ConfirmDialog.tsx`.
- `frontend/src/hooks/useLibrary.ts` — estado da biblioteca e do documento ativo.

**REMOVIDO:** nada.

### Roteamento de estado no frontend

O app passa a ter três seleções: documento ativo, conversa ativa e a visão (upload ou chat). O estado vive em `useLibrary` e é passado por prop — sem biblioteca de estado global, coerente com a decisão de `FEAT-0001` de manter apenas React e Tailwind.

Selecionar um documento limpa a conversa ativa; escolher uma conversa da lista a restaura; "nova conversa" cria uma conversa vazia no documento ativo.

### Limitação de isolamento, declarada

O `session_id` é gerado pelo cliente e enviado em header. Ele **organiza** dados por browser; não **protege** dados. Quem conhecer um `session_id` alheio acessa aqueles documentos. A decisão consciente é aceitar isso num desafio sem autenticação, e:

- filtrar por `session_id` sempre no servidor (princípio 5), para o cliente não conseguir listar tudo;
- responder `404` — nunca `403` — a recurso de outra sessão, para não confirmar existência;
- registrar a limitação no README, com a nota de que autenticação é o próximo passo natural.

## 5. Plano de desenvolvimento por fases

> Cada fase é executável isoladamente por um agente lendo só este documento. **Pré-requisito externo de toda a spec:** `FEAT-0001` e `FEAT-0002` concluídas. Uma fase só inicia quando todas as listadas em "Depende de" estão concluídas.

### Track A — Backend

### Fase A.1 — Listagem e exclusão de documentos *(tamanho M)*

- **id:** `A.1`
- **slug:** `documents-list-api`
- **Objetivo:** expor a biblioteca da sessão e permitir remover um documento com tudo que depende dele.
- **Depende de:** nenhuma
- **Arquivos novos:** `db/003_library_indexes.sql`. **Arquivos alterados:** `backend/app/adapters/repository.py`, `backend/app/api/documents.py`, `backend/app/api/schemas.py`.
- **Passos:** 1) escrever `003_library_indexes.sql` com índice em `documents(session_id, created_at desc)` e as `ON DELETE CASCADE` de `chunks`, `conversations` e `messages`, caso ainda não estejam declaradas; 2) acrescentar ao repositório `list_documents(session_id)` e `delete_document(document_id, session_id)`, ambos com SQL parametrizado e o `delete` dentro de transação; 3) implementar `GET /api/documents` lendo o header `X-Session-Id`; 4) implementar `DELETE /api/documents/{id}` respondendo `404` quando o documento não pertence à sessão; 5) declarar os schemas de resposta em `schemas.py`.
- **Testes:** listagem ordenada e completa (AC-1); isolamento entre sessões (AC-2); cascade remove chunks, conversas e mensagens (AC-3); documento alheio responde `404` e sobrevive (AC-4); exclusão é atômica (AC-5).
- **Escopo travado / violações BLOQUEANTES:** `session_id` só pode vir do header — aceitar por query ou corpo é violação do princípio 5; nenhum SQL concatenado; responder `403` a recurso de outra sessão é violação (confirma existência); não alterar o pipeline de ingestão.
- **Critério de conclusão (gate):** `make down && make up` aplica os três scripts SQL em ordem; testes verdes; `make lint typecheck test` zero.

### Fase A.2 — Listagem de conversas por documento *(tamanho S)*

- **id:** `A.2`
- **slug:** `conversation-persistence`
- **Objetivo:** permitir reencontrar e retomar conversas anteriores de um documento.
- **Depende de:** nenhuma
- **Arquivos novos:** nenhum. **Arquivos alterados:** `backend/app/adapters/repository.py`, `backend/app/api/conversations.py`, `backend/app/api/schemas.py`.
- **Passos:** 1) acrescentar ao repositório `list_conversations(document_id, session_id)`, trazendo id, data e a primeira mensagem do usuário como resumo, ordenadas da mais recente para a mais antiga; 2) implementar `GET /api/documents/{id}/conversations`, respondendo `404` quando o documento não é da sessão; 3) recortar o resumo a um comprimento máximo, sem cortar no meio de palavra; 4) confirmar que `GET /api/conversations/{id}/messages` de `FEAT-0002` já filtra por sessão — se não filtrar, corrigir aqui (é o mínimo necessário, não refatoração).
- **Testes:** conversas listadas com data e resumo (AC-6); documento alheio responde `404` (AC-7); conversa antiga retomável com citações preservadas (AC-8).
- **Escopo travado / violações BLOQUEANTES:** não gerar resumo com LLM — o resumo é a primeira pergunta recortada, e chamar o provedor aqui violaria NFR-1; não expor conversa de outra sessão; nenhum SQL concatenado.
- **Critério de conclusão (gate):** testes verdes; nenhuma chamada ao provedor nas rotas desta fase; `make lint typecheck test` zero.

### Fase A.3 — Testes de isolamento da biblioteca *(tamanho S)*

- **id:** `A.3`
- **slug:** `library-tests`
- **Objetivo:** provar que sessão e documento isolam corretamente e que a exclusão não deixa órfãos.
- **Depende de:** `A.1`, `A.2`
- **Arquivos novos:** `backend/tests/test_library_api.py`. **Arquivos alterados:** `backend/tests/conftest.py` (fixture de duas sessões, se ainda não existir).
- **Passos:** 1) criar fixture que popula duas sessões com documentos e conversas distintos; 2) testar cada rota da spec sob as duas sessões, confirmando isolamento; 3) testar que após `DELETE` não sobram linhas órfãs em `chunks`, `conversations` e `messages`; 4) testar que nenhuma rota desta spec chama o adapter do provedor, usando um fake que falha se invocado; 5) garantir suíte offline.
- **Testes:** AC-2, AC-3, AC-4, AC-5, AC-7, AC-14, AC-15.
- **Escopo travado / violações BLOQUEANTES:** nenhuma chamada de rede real; nenhum `skip` para mascarar flakiness; não testar implementação privada quando a rota cobre o comportamento.
- **Critério de conclusão (gate):** `make test` verde sem `GEMINI_API_KEY`; nenhuma linha órfã após exclusão; `make lint typecheck` zero.

### Track B — Frontend

### Fase B.1 — Barra lateral da biblioteca *(tamanho M)*

- **id:** `B.1`
- **slug:** `library-sidebar`
- **Objetivo:** dar à pessoa a visão de tudo que ela já enviou e a capacidade de trocar de documento.
- **Depende de:** `A.1`
- **Arquivos novos:** `frontend/src/components/LibrarySidebar.tsx`, `frontend/src/components/DocumentItem.tsx`, `frontend/src/hooks/useLibrary.ts`. **Arquivos alterados:** `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`.
- **Passos:** 1) acrescentar a `api.ts` os métodos de listar e excluir documento, e os tipos correspondentes; 2) implementar `useLibrary` com a lista, o documento ativo e o recarregamento após upload ou exclusão; 3) montar a barra lateral com os itens, destacando o ativo; 4) em cada item, mostrar nome, data e estado, reusando `ProcessingStatus` quando o documento está em `processing`; 5) impedir seleção de documento que não esteja `ready`; 6) tratar o estado vazio conduzindo ao upload; 7) manter a barra utilizável em tela estreita.
- **Testes:** estados por documento e bloqueio de seleção do que está processando (AC-9); troca de documento muda o contexto do chat (AC-10); biblioteca vazia mostra o estado inicial (AC-13).
- **Escopo travado / violações BLOQUEANTES:** não instalar biblioteca de estado global nem UI kit; não filtrar documentos no cliente por `session_id` (o servidor já filtra — princípio 5); textos em pt-BR e identificadores em inglês.
- **Critério de conclusão (gate):** upload de dois PDFs e troca entre eles funcionando contra o backend; lint e typecheck zero.

### Fase B.2 — Conversas anteriores *(tamanho M)*

- **id:** `B.2`
- **slug:** `conversation-history`
- **Objetivo:** reencontrar e retomar uma conversa do documento ativo.
- **Depende de:** `A.2`, `B.1`
- **Arquivos novos:** `frontend/src/components/ConversationList.tsx`. **Arquivos alterados:** `frontend/src/hooks/useLibrary.ts`, `frontend/src/components/ChatView.tsx`, `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`.
- **Passos:** 1) acrescentar a `api.ts` a listagem de conversas por documento; 2) renderizar a lista sob o documento ativo, com resumo e data; 3) ao selecionar uma conversa, carregar o histórico por `GET /api/conversations/{id}/messages` e restaurar as mensagens com citações; 4) implementar "nova conversa", criando uma conversa vazia sem apagar as anteriores; 5) destacar a conversa ativa; 6) recarregar a lista quando uma conversa nova recebe a primeira mensagem.
- **Testes:** conversa antiga restaurada com ordem e citações (AC-8); nova conversa não apaga as anteriores (AC-11); trocar de documento troca a lista (AC-10).
- **Escopo travado / violações BLOQUEANTES:** não recarregar a lista a cada token do streaming; não perder o histórico já carregado ao alternar entre conversas; não fabricar resumo no cliente — usar o que vem da `A.2`.
- **Critério de conclusão (gate):** retomar conversa de dois dias de uso simulado exibe o histórico completo; lint e typecheck zero.

### Fase B.3 — Exclusão e acabamento *(tamanho S)*

- **id:** `B.3`
- **slug:** `document-management`
- **Objetivo:** permitir remover um documento com consequência clara, e fechar os estados vazios.
- **Depende de:** `B.1`
- **Arquivos novos:** `frontend/src/components/ConfirmDialog.tsx`. **Arquivos alterados:** `frontend/src/components/DocumentItem.tsx`, `frontend/src/components/LibrarySidebar.tsx`, `frontend/src/lib/errors.ts`.
- **Passos:** 1) implementar o diálogo de confirmação, acessível por teclado e fechável por `Esc`; 2) acrescentar a ação de excluir no item, avisando na confirmação que as conversas do documento serão perdidas; 3) após excluir, atualizar a biblioteca e limpar o documento ativo se era ele; 4) mapear falha de exclusão para mensagem em pt-BR com ação de repetir; 5) cobrir o estado "documento ativo sem conversas" com convite à primeira pergunta.
- **Testes:** confirmação avisa sobre a perda das conversas e a exclusão só ocorre após confirmar (AC-12); estado vazio da biblioteca conduz ao upload (AC-13).
- **Escopo travado / violações BLOQUEANTES:** nunca excluir sem confirmação explícita; não usar `window.confirm`; não exibir stack trace nem corpo bruto de erro; não deixar o app apontando para documento excluído.
- **Critério de conclusão (gate):** ciclo criar → conversar → excluir → biblioteca consistente; lint e typecheck zero.

## 6. Riscos

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| 1 | Prazo acabar antes desta spec começar | Alta | Baixo | É P2 por desenho; `FEAT-0001` e `FEAT-0002` entregam o desafio completo sem ela, e o README a documenta como próximo passo |
| 2 | `ON DELETE CASCADE` faltar nas tabelas de `FEAT-0001`/`FEAT-0002`, deixando órfãos | Média | Médio | `A.1` declara as constraints; `A.3` testa que não sobram órfãos |
| 3 | `session_id` perdido ao limpar o `localStorage`, tornando documentos inacessíveis | Média | Baixo | Documentado no README como limitação; dado permanece no banco, só não é alcançável |
| 4 | Isolamento por sessão confundido com segurança | Média | Alto | Declarado em §4 e no README como limitação conhecida; `404` em vez de `403` evita confirmar existência |
| 5 | Barra lateral quebrar o layout do chat em tela estreita | Média | Baixo | Comportamento responsivo é passo explícito da `B.1` |
| 6 | Refatorar `FEAT-0001`/`FEAT-0002` de passagem e regredir o que já funciona | Média | Alto | Princípio 9 (diff mínimo) e NFR-6; a suíte das specs anteriores roda antes de fechar cada fase |

## 7. Rollout

Sem produção e sem flag. Esta spec só começa depois de `FEAT-0001` e `FEAT-0002` fecharem inteiras — executá-la antes disso é violação do pré-requisito.

`A.1` e `A.2` não dependem uma da outra e podem correr em paralelo. No Track B, `B.1` é o ponto de entrada e depende de `A.1`; `B.3` depende só de `B.1` e pode ser feita antes de `B.2`.

Se o prazo apertar no meio, o ponto de parada limpo é ao fim de `B.1`: biblioteca navegável com troca de documento já é o grosso do valor, e conversas persistidas ficam para depois.

Rollback é `git revert` da fase. Mudança de schema exige `make down` antes do próximo `up`.

## 8. Open Questions

- **OQ-4 — Identidade da sessão anônima.** **RESOLVIDO (2026-08-17):** UUID gerado no browser com `crypto.randomUUID()`, guardado em `localStorage`, enviado no header `X-Session-Id`. *Justificativa:* sem infraestrutura de autenticação, sobrevive a recarregar a página — que é o que "conversas persistidas" exige — e se comporta igual em dev e dentro do Docker. *Rejeitado:* cookie assinado pelo servidor, que exigiria CORS com credenciais e cuidado com `SameSite` atrás do proxy nginx, sem ganho real num app sem contas. *Limitação aceita e documentada:* organiza dados por browser, não os protege.
- **OQ-11 — Escopo da exclusão.** **RESOLVIDO (2026-08-17):** exclusão é permanente e em cascade, com confirmação explícita na UI avisando que as conversas serão perdidas. *Justificativa:* soft delete traria coluna de estado, filtro em toda consulta e uma tela de lixeira — complexidade desproporcional num app sem contas. *Rejeitado:* soft delete e exclusão sem confirmação.
- **OQ-12 — Origem do resumo da conversa na lista.** **RESOLVIDO (2026-08-17):** a primeira pergunta do usuário, recortada. *Justificativa:* é gratuito, previsível e suficiente para reconhecer a conversa; gerar título com LLM gastaria quota do free tier em algo cosmético e violaria NFR-1. *Rejeitado:* título gerado por LLM.
- **OQ-13 — Comportamento ao trocar de documento com conversa aberta.** **ABERTA.** Duas leituras defensáveis: descartar a conversa ativa (mais previsível) ou lembrar a última conversa de cada documento (mais conveniente). Plano: implementar o descarte na `B.1` por ser o comportamento mais simples de explicar, e reavaliar na `B.2` se a retomada por documento aparecer como necessidade real ao usar. Decisão registrada aqui quando resolvida.

## 9. Definition of Done (gate por etapa)

**Gate por fase** — cada uma só fecha com seu critério de conclusão verde:

- [ ] `A.1 documents-list-api` — listagem ordenada, isolamento por sessão, exclusão em cascade e atômica.
- [ ] `A.2 conversation-persistence` — conversas listadas com resumo e retomáveis, sem chamar o provedor.
- [ ] `A.3 library-tests` — isolamento provado nas duas sessões; nenhuma linha órfã após exclusão.
- [ ] `B.1 library-sidebar` — dois PDFs enviados e alternáveis; estado por documento correto.
- [ ] `B.2 conversation-history` — conversa antiga retomada com histórico e citações.
- [ ] `B.3 document-management` — exclusão com confirmação e biblioteca consistente depois.

**Itens globais transversais:**

- [ ] Cada FR desta spec tem ao menos um AC verificado.
- [ ] `make lint`, `make typecheck` e `make test` retornam zero.
- [ ] Nenhum módulo de `backend/app/core/` importa `fastapi`, `asyncpg` ou `google.genai` (princípio 1).
- [ ] O retrieval continua filtrado por `document_id`; nenhuma busca cross-documento foi introduzida (princípio 2).
- [ ] Toda rota filtra `session_id` no servidor, lido do header (princípio 5).
- [ ] Recurso de outra sessão responde `404`, nunca `403`.
- [ ] Todo SQL é parametrizado (princípio 4).
- [ ] Identificadores em inglês; textos de UI em pt-BR (princípio 6).
- [ ] A suíte roda offline, sem chave de API (princípio 7).
- [ ] Nenhuma chamada ao provedor de IA nas rotas desta spec (NFR-1).
- [ ] README documenta o isolamento por sessão como limitação conhecida (NFR-5).
- [ ] Nenhuma regressão em `FEAT-0001` e `FEAT-0002`: upload, ingestão e chat seguem funcionando (princípio 9, NFR-6).
