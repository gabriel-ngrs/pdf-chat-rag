---
id: FEAT-0002
slug: chat-rag
title: "Chat conversacional com RAG: retrieval, memória de sessão, citações e streaming"
type: feature
status: draft
priority: P0
size: L
wave: multi
domain: fullstack
bounded_context: rag
cross_context: [ingestion]
created_at: 2026-08-17
updated_at: 2026-08-17
owner: gabriel
depends_on: [FEAT-0001]
blocks: [FEAT-0003]
quality_gate:
  scorer: phase-evaluator
  threshold: 8.5
---

# FEAT-0002 — Chat com RAG

> **Nota de planning (2026-08-17):** spec construída após sondagem do repositório. **Pré-requisito externo:** `FEAT-0001` (ingestão) concluída até a fase `A.5` — sem chunks embedados no pgvector não há o que recuperar. O que é **REUSADO** desta base: `backend/app/core/models.py`, `backend/app/adapters/{db,gemini,repository}.py`, `backend/app/config.py`, `backend/app/main.py`, `frontend/src/lib/{api,session,types}.ts`, e o `frontend/nginx.conf` que já traz `proxy_buffering off` — o SSE desta spec depende disso.
>
> **Fora do escopo desta spec:** upload e ingestão (`FEAT-0001`); biblioteca de múltiplos documentos e retomada de conversas antigas (`FEAT-0003`); busca cross-documento; autenticação; re-ranking com modelo dedicado; observabilidade.

## Resumo executivo (TL;DR)

| | |
|---|---|
| **O quê** | A pessoa conversa com o documento processado: pergunta, recebe resposta em streaming fundamentada nos trechos recuperados, com citação de página, e o chat entende perguntas de continuação. |
| **Por quê** | É o requisito 2 do desafio e o eixo mais pesado da avaliação: chunking, embeddings, retrieval, montagem de prompt e fundamentação. |
| **Backend-Infra** | Tabelas de conversa e mensagem; condensação de pergunta; busca vetorial com limiar; montagem de prompt; endpoint SSE; mini-eval de `recall@k`. |
| **Frontend** | Chat com render incremental do streaming, histórico da sessão, chips de citação com página e trecho, e estados de erro. |
| **Decisão** | Retrieval sempre filtrado por `document_id`; abaixo do limiar de similaridade o sistema recusa em vez de alucinar; memória é janela de 6 mensagens + condensação da pergunta. |
| **Tamanho** | L — 7 fases no Track A (backend) e 4 no Track B (frontend). |

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

Com o documento ingerido pela `FEAT-0001`, o banco tem chunks vetorizados e citáveis por página. Falta a parte que o desafio avalia com mais peso: transformar uma pergunta em linguagem natural numa resposta que **comprovadamente veio do documento**.

Dois detalhes do enunciado carregam a maior parte da dificuldade e são fáceis de subestimar:

**"Compreender perguntas de continuação."** Quando alguém pergunta *"e quanto a isso?"* logo depois de *"quais serviços a YAITEC oferece?"*, buscar por *"e quanto a isso?"* no índice vetorial não recupera nada — o pronome não carrega semântica. A solução é condensar a pergunta usando o histórico numa query autocontida antes de buscar. Sem esse passo, a memória da conversa existe no prompt mas **não existe no retrieval**, e a resposta degrada exatamente nas perguntas de acompanhamento.

**"Respostas fundamentadas, citando o trecho ou a página."** Fundamentação não é só instruir o modelo a citar; é decidir o que fazer quando o documento não contém a resposta. Por isso o limiar de similaridade e a recusa explícita são requisitos, não refinamento.

O seam de infraestrutura já está pronto: `frontend/nginx.conf` foi escrito com `proxy_buffering off` na `location /api/` justamente para o streaming desta spec passar sem ser bufferizado pelo proxy.

Sobre o free tier: o gargalo aqui muda de lugar. Embeddings de query são baratos (um texto curto por pergunta); quem aperta é o chat, com **~10 RPM** no `gemini-2.5-flash`. Perguntas em rajada batem em `429` — que precisa virar mensagem clara em pt-BR, não erro cru.

### 1.1 Princípios invioláveis

1. **`backend/app/core/` não importa `fastapi`, `asyncpg` nem `google.genai`.** Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`. Aqui isso vale para condensação, seleção de top-k e montagem de prompt — os três são puros e testáveis offline.
2. **Frameworks de RAG são proibidos.** Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`. O pipeline é escrito no projeto.
3. **Toda resposta do chat retorna citações estruturadas com página e trecho, em campo próprio do payload** — não apenas embutidas no texto gerado. Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`.
4. **Quando nenhum chunk passa do limiar de similaridade, a API responde com recusa explícita em vez de gerar resposta sem fundamento no PDF.** Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`.
5. **Segredos só em variável de ambiente, nunca em log ou mensagem de exceção.** Origem: `.codeflow/constitution.md` + rule universal `security`.
6. **Toda entrada externa é validada no servidor.** Origem: rule universal `security`, `## Regras`.
7. **SQL parametrizado; nunca concatenação com input externo.** Origem: rule universal `security`, `## Anti-regras`.
8. **Identificadores em inglês; mensagens ao usuário em pt-BR.** Origem: rule universal `naming`, `## Regras`.
9. **Todo código novo tem teste; teste é determinístico e descreve comportamento.** Origem: rule universal `testing`, `## Regras`.
10. **`mypy --strict` e `tsc` strict zerados, sem afrouxar gate.** Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`.

## 2. Requisitos

### Funcionais

- **FR-1** — `POST /api/conversations` cria uma conversa vinculada a um `document_id` e ao `session_id` do header `X-Session-Id`. Documento que não esteja em `ready` é recusado com mensagem em pt-BR.
- **FR-2** — `POST /api/conversations/{id}/messages` recebe a pergunta e responde por SSE, emitindo os tokens da resposta incrementalmente.
- **FR-3** — Antes do retrieval, a pergunta é condensada numa query autocontida usando as últimas `HISTORY_WINDOW` mensagens (default 6). Perguntas já autocontidas passam sem reescrita desnecessária.
- **FR-4** — O retrieval busca por similaridade de cosseno no pgvector, **sempre filtrando por `document_id`** da conversa, retornando os `RETRIEVAL_TOP_K` melhores chunks (default 5).
- **FR-5** — Chunks com similaridade abaixo de `SIMILARITY_THRESHOLD` são descartados. Se nenhum sobrevive, a API não chama o LLM: responde com a recusa padrão em pt-BR e citações vazias.
- **FR-6** — O prompt é montado com os chunks sobreviventes identificados por página, a janela de histórico e a instrução de responder apenas com base no contexto fornecido.
- **FR-7** — A resposta termina com um evento SSE de citações estruturadas: lista de `{page_number, snippet, chunk_index, score}` dos chunks efetivamente usados.
- **FR-8** — Pergunta e resposta são persistidas em `messages`, preservando a ordem e as citações associadas à resposta.
- **FR-9** — `GET /api/conversations/{id}/messages` devolve o histórico da conversa, permitindo reconstruir a tela após recarregar a página.
- **FR-10** — Erro do provedor (`429`, timeout, indisponibilidade) é emitido como evento SSE de erro com mensagem em pt-BR, sem derrubar a conexão de forma opaca.
- **FR-11** — Existe um mini-eval de retrieval: um conjunto versionado de perguntas com a página esperada, rodável por `make eval`, que reporta `recall@k` e a similaridade média.
- **FR-12** — A UI de chat exibe as mensagens em ordem, com a resposta do assistente renderizada incrementalmente conforme o streaming chega.
- **FR-13** — Cada resposta exibe suas citações como elementos clicáveis que revelam o trecho de origem e a página.
- **FR-14** — A UI mostra estado de "pensando" entre o envio e o primeiro token, e permite cancelar uma resposta em andamento.
- **FR-15** — A recusa por falta de fundamento é exibida de forma distinta de um erro técnico — é uma resposta legítima, não uma falha.

### Não-funcionais

- **NFR-1** — O primeiro token da resposta chega em ≤ 5 s em condições normais de free tier.
- **NFR-2** — Condensação, seleção de top-k e montagem de prompt vivem em `backend/app/core/` e são testáveis sem rede e sem banco.
- **NFR-3** — Nenhuma chave de API aparece em log, resposta ou evento SSE.
- **NFR-4** — `make lint`, `make typecheck` e `make test` retornam zero; a suíte roda offline.
- **NFR-5** — A janela de histórico é limitada por `HISTORY_WINDOW`, de modo que o prompt não cresce indefinidamente com a conversa.
- **NFR-6** — `RETRIEVAL_TOP_K`, `SIMILARITY_THRESHOLD`, `HISTORY_WINDOW` e os ids de modelo são configuráveis por env.
- **NFR-7** — O `recall@k` do mini-eval sobre o PDF de exemplo é ≥ 0,8 com a configuração default.

## 3. Critérios de aceite

- **AC-1** (FR-1) — *Dado* um documento em `processing`, *quando* tento criar conversa, *então* recebo `409` com mensagem em pt-BR dizendo que o documento ainda está sendo processado.
- **AC-2** (FR-2, FR-12) — *Dado* uma conversa válida, *quando* envio "quais serviços a YAITEC oferece?", *então* recebo eventos SSE de token que, concatenados, formam a resposta, e a UI a renderiza incrementalmente.
- **AC-3** (FR-3) — *Dado* o histórico `["quais serviços a YAITEC oferece?", "<resposta>"]`, *quando* envio "e quanto a isso?", *então* a query condensada enviada ao retrieval é autocontida e menciona os serviços da YAITEC, não o pronome.
- **AC-4** (FR-3) — *Dado* uma pergunta já autocontida como "qual o endereço da empresa?", *quando* a condensação roda, *então* a query preservada é semanticamente equivalente à original.
- **AC-5** (FR-4) — *Dado* dois documentos ingeridos, *quando* pergunto numa conversa do documento A, *então* nenhum chunk do documento B aparece nas citações.
- **AC-6** (FR-4) — *Dado* `RETRIEVAL_TOP_K=5`, *quando* o retrieval roda, *então* no máximo 5 chunks são considerados, ordenados por similaridade decrescente.
- **AC-7** (FR-5) — *Dado* uma pergunta sem relação alguma com o documento, *quando* nenhum chunk passa de `SIMILARITY_THRESHOLD`, *então* a resposta é a recusa padrão em pt-BR, as citações vêm vazias e **nenhuma chamada ao LLM é feita**.
- **AC-8** (FR-6) — *Dado* três chunks recuperados, *quando* o prompt é montado, *então* ele contém os três trechos identificados por página e a instrução de responder apenas com base neles.
- **AC-9** (FR-7) — *Dado* uma resposta fundamentada, *quando* o streaming termina, *então* chega um evento de citações com `page_number`, `snippet`, `chunk_index` e `score` de cada chunk usado.
- **AC-10** (FR-8, FR-9) — *Dado* uma conversa com três trocas, *quando* consulto `GET /api/conversations/{id}/messages`, *então* recebo as seis mensagens na ordem correta, com as citações presas às respostas.
- **AC-11** (FR-10) — *Dado* que o provedor retorna `429`, *quando* a resposta está sendo gerada, *então* chega um evento SSE de erro com mensagem em pt-BR sobre limite de uso, e a conexão fecha de forma limpa.
- **AC-12** (FR-11, NFR-7) — *Dado* o conjunto de eval versionado, *quando* rodo `make eval`, *então* o relatório mostra `recall@k` ≥ 0,8 e a similaridade média por pergunta.
- **AC-13** (FR-13) — *Dado* uma resposta com duas citações, *quando* clico numa delas, *então* vejo o trecho de origem e o número da página.
- **AC-14** (FR-14) — *Dado* que enviei uma pergunta, *quando* ainda não chegou o primeiro token, *então* vejo indicador de "pensando"; e ao cancelar, o streaming para e a UI volta ao estado utilizável.
- **AC-15** (FR-15) — *Dado* uma recusa por falta de fundamento, *quando* ela é exibida, *então* aparece como resposta do assistente com aparência distinta de erro técnico, sem banner vermelho de falha.
- **AC-16** (NFR-5) — *Dado* uma conversa com 20 mensagens e `HISTORY_WINDOW=6`, *quando* o prompt é montado, *então* ele inclui no máximo as 6 últimas.
- **AC-17** (NFR-3) — *Dado* qualquer caminho de erro do adapter, *quando* inspeciono logs e eventos SSE, *então* nenhuma chave de API aparece.
- **AC-18** (NFR-4) — *Dado* nenhuma `GEMINI_API_KEY` no ambiente, *quando* rodo `make test`, *então* a suíte passa inteira.

## 4. Abordagem técnica

### Mapa NOVO vs. REUSADO vs. REMOVIDO

**REUSADO** (existe após `FEAT-0001`; nesta spec é consumido ou estendido, nunca duplicado):

| Caminho | Como é reusado |
|---|---|
| `backend/app/adapters/gemini.py` | Ganha geração e `embed_query`; o mecanismo de batch, backoff e pool de chaves já existe e não é reimplementado. |
| `backend/app/adapters/repository.py` | Ganha os métodos de conversa e de busca vetorial, no mesmo padrão de SQL parametrizado. |
| `backend/app/adapters/db.py` | Pool `asyncpg` consumido como está. |
| `backend/app/core/models.py` | Ganha `RetrievedChunk`, `Citation`, `Message`. |
| `backend/app/config.py` | Ganha as variáveis de retrieval e de chat. |
| `backend/app/main.py` | Registra o router de conversas. |
| `db/` | Recebe `002_conversations.sql`; o seam de `docker-entrypoint-initdb.d` já existe. |
| `frontend/src/lib/api.ts` | Ganha o cliente SSE; o wrapper de `fetch` e o header `X-Session-Id` já existem. |
| `frontend/src/lib/types.ts` | Ganha os tipos de conversa, mensagem e citação. |
| `frontend/nginx.conf` | Consumido como está — `proxy_buffering off` já preparado para SSE. |
| `Makefile` | Alterado para acrescentar o alvo `eval`. |
| `.env.example` | Alterado para documentar as variáveis novas. |

**NOVO:**

- `db/002_conversations.sql` — tabelas `conversations` e `messages`.
- `backend/app/core/condensation.py` — construção do prompt de condensação e decisão de quando condensar.
- `backend/app/core/retrieval.py` — filtragem por limiar, ordenação e seleção de top-k (puro, sobre resultados já trazidos do banco).
- `backend/app/core/prompt.py` — montagem do prompt final com contexto, histórico e instrução de fundamentação.
- `backend/app/api/conversations.py` — rotas de conversa e o endpoint SSE.
- `backend/app/chat.py` — orquestração: condensar → embedar query → buscar → filtrar → montar prompt → streamar → persistir.
- `backend/eval/dataset.json`, `backend/eval/run_eval.py` — mini-eval de `recall@k`.
- `backend/tests/test_condensation.py`, `test_retrieval.py`, `test_prompt.py`, `test_chat_api.py`.
- `frontend/src/components/ChatView.tsx`, `MessageList.tsx`, `MessageInput.tsx`, `CitationChip.tsx`.
- `frontend/src/hooks/useChat.ts`, `frontend/src/lib/sse.ts`.

**REMOVIDO:** nada.

### Modelo de dados

```sql
conversations(id uuid pk, document_id uuid fk, session_id text, created_at timestamptz)
messages(id bigserial pk, conversation_id uuid fk, role text, content text,
         citations jsonb, created_at timestamptz)
```

`citations` como `jsonb` na mensagem do assistente: a citação é um fato daquela resposta, não uma entidade com vida própria — normalizar acrescentaria uma tabela sem ganho de consulta.

### Pipeline de uma pergunta

```
pergunta + histórico
  → condensação (core, 1 chamada barata ao LLM só quando há histórico)
  → embed_query (adapter)
  → busca vetorial filtrada por document_id (repositório, SQL parametrizado)
  → filtro por SIMILARITY_THRESHOLD + top-k (core, puro)
  → [nenhum sobrevivente] → recusa em pt-BR, sem chamar o LLM
  → montagem de prompt (core, puro)
  → geração em streaming (adapter) → eventos SSE de token
  → evento SSE de citações → persistência de pergunta e resposta
```

Os três passos marcados como `core` são puros: recebem dados, devolvem dados, não tocam rede nem banco. É isso que torna o núcleo do RAG testável offline e o que sustenta o princípio 1.

### Protocolo SSE

| Evento | Payload |
|---|---|
| `token` | `{"text": "..."}` — fragmento da resposta |
| `citations` | `{"citations": [{page_number, snippet, chunk_index, score}]}` |
| `error` | `{"message": "<pt-BR>", "code": "rate_limit\|provider\|internal"}` |
| `done` | `{"message_id": "..."}` |

### Restrições de free tier e como o desenho responde

| Restrição | Efeito | Resposta no desenho |
|---|---|---|
| Chat ~10 RPM | Perguntas em rajada batem em `429` | Evento SSE de erro com mensagem em pt-BR (FR-10); UI oferece repetir |
| Condensação gasta uma chamada extra | Dobraria o consumo por pergunta | Condensar só quando há histórico; pergunta autocontida sem histórico pula o passo |
| Recusa abaixo do limiar | — | Economiza chamada ao LLM: sem chunk relevante, não há geração (FR-5) |
| Chat ~250k TPM | Histórico crescente inflaria o prompt | `HISTORY_WINDOW` limita a janela (NFR-5) |

### Configuração acrescentada

`GEMINI_CHAT_MODEL`, `RETRIEVAL_TOP_K`, `SIMILARITY_THRESHOLD`, `HISTORY_WINDOW`, `CHAT_TIMEOUT_SECONDS`.

## 5. Plano de desenvolvimento por fases

> Cada fase é executável isoladamente por um agente lendo só este documento. **Pré-requisito externo de toda a spec:** `FEAT-0001` concluída até `A.5`. Uma fase só inicia quando todas as listadas em "Depende de" estão concluídas.

### Track A — Backend

### Fase A.1 — Schema e repositório de conversas *(tamanho S)*

- **id:** `A.1`
- **slug:** `conversation-schema`
- **Objetivo:** persistir conversas e mensagens vinculadas a documento e sessão.
- **Depende de:** nenhuma
- **Arquivos novos:** `db/002_conversations.sql`, `backend/tests/test_conversation_repository.py`. **Arquivos alterados:** `backend/app/adapters/repository.py`, `backend/app/core/models.py`.
- **Passos:** 1) escrever `002_conversations.sql` com as tabelas de §4 e índices por `document_id` e `session_id`; 2) acrescentar ao repositório, com SQL parametrizado, os métodos de criar conversa, buscar conversa por id, inserir mensagem e listar mensagens ordenadas; 3) definir `Message` e `Citation` em `core/models.py` como dataclasses puras; 4) serializar citações em `jsonb` na inserção e desserializar na leitura.
- **Testes:** round-trip de conversa e mensagens preservando ordem e citações (AC-10); conversa de outra sessão não é acessível.
- **Escopo travado / violações BLOQUEANTES:** não usar ORM; não concatenar SQL; `core/models.py` não pode importar `asyncpg`; não implementar rota nesta fase.
- **Critério de conclusão (gate):** `make down && make up` aplica os dois scripts SQL em ordem; testes verdes; `make lint typecheck test` zero.

### Fase A.2 — Condensação de pergunta de continuação *(tamanho M)*

- **id:** `A.2`
- **slug:** `query-condensation`
- **Objetivo:** transformar pergunta dependente de contexto numa query autocontida, para o retrieval funcionar em perguntas de continuação.
- **Depende de:** nenhuma
- **Arquivos novos:** `backend/app/core/condensation.py`, `backend/tests/test_condensation.py`. **Arquivos alterados:** `backend/app/config.py` (`HISTORY_WINDOW`).
- **Passos:** 1) implementar `should_condense(history) -> bool` — sem histórico, não condensa; 2) implementar `build_condensation_prompt(history, question) -> str`, usando no máximo `HISTORY_WINDOW` mensagens e instruindo o modelo a devolver só a pergunta reescrita, em pt-BR; 3) implementar `select_history_window(messages, window) -> list[Message]`; 4) manter tudo puro — a chamada ao LLM acontece no orquestrador da `A.5`, não aqui.
- **Testes:** pronome resolvido a partir do histórico (AC-3); pergunta autocontida preservada (AC-4); janela limitada a `HISTORY_WINDOW` (AC-16); sem histórico, `should_condense` é falso.
- **Escopo travado / violações BLOQUEANTES:** módulo não pode importar `google.genai`, `fastapi` ou `asyncpg` (princípio 1); não fazer chamada de rede; não usar framework de RAG (princípio 2).
- **Critério de conclusão (gate):** testes verdes sem rede; `make lint typecheck test` zero.

### Fase A.3 — Retrieval com limiar *(tamanho M)*

- **id:** `A.3`
- **slug:** `retrieval`
- **Objetivo:** recuperar os chunks mais relevantes do documento da conversa e descartar o que não sustenta resposta.
- **Depende de:** nenhuma
- **Arquivos novos:** `backend/app/core/retrieval.py`, `backend/tests/test_retrieval.py`. **Arquivos alterados:** `backend/app/adapters/repository.py`, `backend/app/core/models.py` (`RetrievedChunk`), `backend/app/config.py`.
- **Passos:** 1) acrescentar ao repositório a busca vetorial com SQL parametrizado, ordenando por distância de cosseno e **filtrando por `document_id`**, com `LIMIT` derivado de `RETRIEVAL_TOP_K`; 2) converter distância em score de similaridade normalizado; 3) implementar em `core/retrieval.py` a filtragem por `SIMILARITY_THRESHOLD`, a ordenação e o corte em top-k — puro, sobre a lista já trazida; 4) expor `has_grounding(chunks) -> bool` para o orquestrador decidir pela recusa.
- **Testes:** isolamento por documento (AC-5); no máximo top-k, ordenados (AC-6); tudo abaixo do limiar resulta em lista vazia e `has_grounding` falso (AC-7).
- **Escopo travado / violações BLOQUEANTES:** o filtro por `document_id` é obrigatório e não pode ser opcional nesta spec (OQ-2 resolvida); `core/retrieval.py` não toca banco; nenhum SQL concatenado.
- **Critério de conclusão (gate):** testes verdes; busca real contra o banco retorna chunks do documento certo; `make lint typecheck test` zero.

### Fase A.4 — Montagem do prompt *(tamanho S)*

- **id:** `A.4`
- **slug:** `prompt-assembly`
- **Objetivo:** produzir o prompt que fundamenta a resposta nos trechos recuperados e nomeia as páginas.
- **Depende de:** `A.3`
- **Arquivos novos:** `backend/app/core/prompt.py`, `backend/tests/test_prompt.py`. **Arquivos alterados:** nenhum.
- **Passos:** 1) implementar `build_answer_prompt(chunks, history, question) -> str`; 2) inserir cada chunk delimitado e rotulado com sua página; 3) incluir instrução explícita de responder apenas com base no contexto e de indicar a página; 4) incluir a janela de histórico já recortada pela `A.2`; 5) definir a constante da mensagem de recusa em pt-BR, usada quando não há fundamento.
- **Testes:** prompt contém os trechos com as páginas e a instrução de fundamentação (AC-8); histórico respeitado (AC-16); prompt é determinístico para a mesma entrada.
- **Escopo travado / violações BLOQUEANTES:** módulo puro — sem rede, sem banco, sem `fastapi`; não incluir dado de outro documento; não injetar conteúdo de usuário sem delimitação clara do bloco de contexto.
- **Critério de conclusão (gate):** testes verdes; `make lint typecheck test` zero.

### Fase A.5 — Endpoint de chat com streaming *(tamanho L)*

- **id:** `A.5`
- **slug:** `chat-endpoint`
- **Objetivo:** amarrar o pipeline inteiro numa rota SSE que responde incrementalmente e persiste a conversa.
- **Depende de:** `A.1`, `A.2`, `A.4`
- **Arquivos novos:** `backend/app/api/conversations.py`, `backend/app/chat.py`. **Arquivos alterados:** `backend/app/main.py`, `backend/app/adapters/gemini.py` (geração em streaming e `embed_query`), `backend/app/api/schemas.py`, `backend/app/config.py`.
- **Passos:** 1) acrescentar ao adapter Gemini `embed_query` e `stream_answer(prompt) -> AsyncIterator[str]`, reusando o backoff e o pool já existentes; 2) implementar `POST /api/conversations` validando que o documento está `ready` e pertence à sessão; 3) implementar `POST /api/conversations/{id}/messages` como `StreamingResponse` SSE; 4) orquestrar em `chat.py`: condensar (só se houver histórico) → `embed_query` → buscar → filtrar → se sem fundamento, emitir a recusa e encerrar **sem chamar o LLM** → senão montar prompt e streamar; 5) emitir o evento `citations` ao fim e depois `done`; 6) persistir pergunta e resposta com as citações; 7) mapear erro do provedor para evento `error` com mensagem em pt-BR e código; 8) implementar `GET /api/conversations/{id}/messages`.
- **Testes:** streaming concatenado forma a resposta (AC-2); recusa sem chamar LLM (AC-7); evento de citações completo (AC-9); histórico recuperável (AC-10); `429` vira evento de erro limpo (AC-11); documento não-`ready` recusado (AC-1); chave nunca vaza (AC-17).
- **Escopo travado / violações BLOQUEANTES:** nenhuma chamada ao Gemini fora do adapter; não bufferizar a resposta inteira antes de emitir (destrói o propósito do SSE); não persistir resposta parcial como se fosse completa quando o stream falha; não expor `document_id` ou conversa de outra sessão.
- **Critério de conclusão (gate):** pergunta real sobre o PDF de exemplo retorna resposta em streaming com citação de página correta; `make lint typecheck test` zero.

### Fase A.6 — Mini-eval de retrieval *(tamanho M)*

- **id:** `A.6`
- **slug:** `rag-eval`
- **Objetivo:** **medir** a qualidade do retrieval, não só construí-lo.
- **Depende de:** `A.3`
- **Arquivos novos:** `backend/eval/dataset.json`, `backend/eval/run_eval.py`, `backend/eval/README.md`. **Arquivos alterados:** `Makefile` (alvo `eval`).
- **Passos:** 1) montar `dataset.json` com 8 a 12 perguntas sobre o PDF de exemplo da YAITEC, cada uma com a página esperada; 2) implementar `run_eval.py` que ingere o PDF de exemplo, roda o retrieval de cada pergunta e calcula `recall@k` (a página esperada aparece entre os top-k) e a similaridade média; 3) imprimir relatório por pergunta e agregado, com código de saída não-zero se `recall@k` cair abaixo do mínimo configurado; 4) acrescentar `eval:` ao `Makefile`; 5) documentar em `backend/eval/README.md` o que é medido e como interpretar.
- **Testes:** `make eval` roda ponta a ponta e reporta `recall@k` ≥ 0,8 (AC-12); o script falha com saída não-zero quando o limiar não é atingido.
- **Escopo travado / violações BLOQUEANTES:** o eval **não** entra em `make check` — ele consome quota real e não pode ser gate de CI local; não commitar chave no dataset; não ajustar o dataset para inflar a métrica.
- **Critério de conclusão (gate):** `make eval` executa e reporta; `backend/eval/README.md` explica a métrica; `make lint typecheck` zero.

### Fase A.7 — Testes de integração do chat *(tamanho M)*

- **id:** `A.7`
- **slug:** `chat-tests`
- **Objetivo:** provar o comportamento do chat com LLM falso, offline e determinístico.
- **Depende de:** `A.5`
- **Arquivos novos:** `backend/tests/test_chat_api.py`. **Arquivos alterados:** `backend/tests/fakes.py`, `backend/tests/conftest.py`.
- **Passos:** 1) estender o fake de `FEAT-0001` com geração em streaming determinística e condensação previsível; 2) testar o fluxo completo criar conversa → perguntar → receber tokens → citações → histórico persistido; 3) testar a recusa por falta de fundamento, verificando que o LLM **não** foi chamado; 4) testar pergunta de continuação, verificando a query condensada que chegou ao retrieval; 5) testar o mapeamento de `429` para evento de erro; 6) garantir suíte offline.
- **Testes:** AC-2, AC-3, AC-7, AC-9, AC-10, AC-11, AC-17, AC-18.
- **Escopo travado / violações BLOQUEANTES:** nenhuma chamada de rede real; nenhum `skip` para mascarar flakiness; não asserir sobre o texto exato gerado por LLM real (não-determinístico) — asserir sobre estrutura e sobre o que foi passado aos colaboradores.
- **Critério de conclusão (gate):** `make test` verde sem `GEMINI_API_KEY`; `make lint typecheck` zero.

### Track B — Frontend

### Fase B.1 — Tela de chat *(tamanho M)*

- **id:** `B.1`
- **slug:** `chat-view`
- **Objetivo:** estrutura visual da conversa, ainda sem streaming.
- **Depende de:** nenhuma
- **Arquivos novos:** `frontend/src/components/ChatView.tsx`, `frontend/src/components/MessageList.tsx`, `frontend/src/components/MessageInput.tsx`. **Arquivos alterados:** `frontend/src/App.tsx`, `frontend/src/lib/types.ts`.
- **Passos:** 1) declarar em `types.ts` os tipos de conversa, mensagem e citação, espelhando os schemas da `A.5`; 2) montar o layout do chat com lista rolável e campo de entrada fixo; 3) diferenciar visualmente mensagem do usuário e do assistente; 4) desabilitar o envio com entrada vazia ou resposta em andamento; 5) rolar automaticamente para a última mensagem, sem sequestrar o scroll quando o usuário subiu para ler.
- **Testes:** `tsc --noEmit` e `npm run lint` zero; lista renderiza histórico mockado na ordem correta.
- **Escopo travado / violações BLOQUEANTES:** não instalar biblioteca de UI kit nem de estado; textos em pt-BR e identificadores em inglês (princípio 8); não afrouxar `strict`.
- **Critério de conclusão (gate):** tela navegável com dados mockados; lint e typecheck zero.

### Fase B.2 — Streaming da resposta *(tamanho M)*

- **id:** `B.2`
- **slug:** `streaming`
- **Objetivo:** consumir o SSE e renderizar a resposta enquanto ela é gerada.
- **Depende de:** `B.1`, `A.5`
- **Arquivos novos:** `frontend/src/lib/sse.ts`, `frontend/src/hooks/useChat.ts`. **Arquivos alterados:** `frontend/src/components/ChatView.tsx`.
- **Passos:** 1) implementar em `sse.ts` o consumo do stream via `fetch` + `ReadableStream`, com parsing dos quatro tipos de evento de §4 (necessário porque `EventSource` não suporta `POST` nem headers); 2) implementar `useChat` acumulando tokens numa mensagem em construção; 3) ao receber `citations`, prender as citações à mensagem; 4) implementar cancelamento via `AbortController`; 5) mostrar indicador de "pensando" entre o envio e o primeiro token.
- **Testes:** tokens concatenados aparecem incrementalmente (AC-2); indicador de pensando e cancelamento funcionam (AC-14).
- **Escopo travado / violações BLOQUEANTES:** não aguardar o stream inteiro para só então renderizar; não deixar `AbortController` órfão ao desmontar; não usar `EventSource` (não atende ao `POST` com header de sessão).
- **Critério de conclusão (gate):** resposta real renderiza token a token contra o backend rodando; lint e typecheck zero.

### Fase B.3 — Citações na interface *(tamanho M)*

- **id:** `B.3`
- **slug:** `citations`
- **Objetivo:** tornar a fundamentação visível e verificável pelo usuário.
- **Depende de:** `B.2`
- **Arquivos novos:** `frontend/src/components/CitationChip.tsx`. **Arquivos alterados:** `frontend/src/components/MessageList.tsx`.
- **Passos:** 1) renderizar sob cada resposta os chips de citação rotulados com a página; 2) ao clicar, expandir o `snippet` de origem; 3) ordenar por página e remover duplicatas da mesma página quando o trecho for o mesmo; 4) tratar o caso de zero citações (recusa) sem renderizar área vazia; 5) garantir chip acessível — elemento focável, com rótulo descritivo.
- **Testes:** clique revela trecho e página (AC-13); resposta sem citação não exibe área de citações (AC-15).
- **Escopo travado / violações BLOQUEANTES:** não exibir o chunk inteiro sem recorte (polui a leitura); não fabricar citação no cliente — só renderizar o que veio no evento `citations`.
- **Critério de conclusão (gate):** citações reais de uma pergunta sobre o PDF de exemplo exibidas e expansíveis; lint e typecheck zero.

### Fase B.4 — Erros e recusa na interface *(tamanho S)*

- **id:** `B.4`
- **slug:** `chat-errors`
- **Objetivo:** distinguir recusa legítima de falha técnica e tornar toda falha acionável.
- **Depende de:** `B.3`
- **Arquivos novos:** nenhum. **Arquivos alterados:** `frontend/src/lib/errors.ts`, `frontend/src/components/ChatView.tsx`, `frontend/src/components/MessageList.tsx`.
- **Passos:** 1) mapear os códigos do evento `error` (`rate_limit`, `provider`, `internal`) para mensagens em pt-BR com ação sugerida; 2) renderizar erro técnico como banner com botão de repetir, preservando a pergunta digitada; 3) renderizar a recusa por falta de fundamento como mensagem normal do assistente, com marcação sutil e **sem** aparência de erro; 4) cobrir o estado vazio da conversa com sugestão de primeira pergunta; 5) tratar queda de conexão no meio do stream, preservando o texto já recebido.
- **Testes:** `429` vira mensagem de limite com ação de repetir (AC-11); recusa aparece como resposta, não como erro (AC-15).
- **Escopo travado / violações BLOQUEANTES:** nunca exibir stack trace, código de exceção ou chave; não perder a pergunta do usuário quando o envio falha; não usar `alert()`.
- **Critério de conclusão (gate):** cada código de erro reproduzido manualmente exibe a mensagem correta; lint e typecheck zero.

## 6. Riscos

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| 1 | `SIMILARITY_THRESHOLD` mal calibrado — recusa demais ou fundamenta de menos | Alta | Alto | O mini-eval da `A.6` mede o efeito da calibração; valor é env e ajustável sem redeploy |
| 2 | Condensação piorar perguntas já autocontidas | Média | Médio | `should_condense` pula quando não há histórico; AC-4 cobre a preservação |
| 3 | Buffering em algum ponto do caminho matar o streaming | Média | Alto | `nginx.conf` já tem `proxy_buffering off`; a `B.2` valida contra o compose real, não só em dev |
| 4 | `429` do chat (~10 RPM) durante a demonstração | Média | Médio | Evento de erro com mensagem clara e ação de repetir; pool opcional de chaves da `FEAT-0001` |
| 5 | Condensação dobrar o consumo de requisições por pergunta | Média | Médio | Só condensa com histórico; recusa por falta de fundamento economiza a chamada de geração |
| 6 | Contrato SSE divergir entre os tracks | Média | Médio | Protocolo tabelado em §4 é a fonte única; `B.2` depende explicitamente de `A.5` |
| 7 | Resposta parcial persistida como completa se o stream cai | Baixa | Médio | Escopo travado da `A.5` proíbe; a persistência acontece após o fim do stream |

## 7. Rollout

Sem produção e sem flag. A ordem é a das fases, com `A.1`, `A.2` e `A.3` podendo correr em paralelo — nenhuma depende das outras. `A.4` fecha o núcleo puro; `A.5` amarra tudo e é o primeiro ponto em que o chat existe de fato.

No Track B, `B.1` pode ser feita a qualquer momento; `B.2` é o ponto de acoplamento com `A.5`.

A `A.6` (eval) depende só de `A.3` e pode ser feita cedo — quanto antes existir, mais cedo a calibração do limiar deixa de ser palpite.

Rollback é `git revert` da fase. Mudança de schema exige `make down` antes do próximo `up`.

## 8. Open Questions

- **OQ-2 — Escopo do retrieval com múltiplos documentos.** **RESOLVIDO (2026-08-17):** retrieval sempre filtrado pelo `document_id` da conversa. *Justificativa:* o desafio pede "conversa sobre o PDF", no singular; filtrar por documento deixa a citação inequívoca ("página 4", sem ambiguidade de fonte) e mantém a fundamentação limpa, que é o eixo avaliado. Também é o caminho de menos trabalho. *Rejeitado:* busca em toda a biblioteca (respostas misturam fontes que não deveriam se misturar) e toggle híbrido (dobra os casos de teste do retrieval e da UI de citação). *Nota:* `document_id` já está no schema desde a `FEAT-0001`, então ampliar depois é incremento, não refatoração.
- **OQ-3 — Estratégia de memória da conversa.** **RESOLVIDO (2026-08-17):** janela deslizante das últimas 6 mensagens (`HISTORY_WINDOW`) mais condensação da pergunta numa query autocontida antes do retrieval. *Justificativa:* sem a condensação, a memória existe no prompt mas não no retrieval — perguntas de continuação com pronome não recuperam nada, que é exatamente o requisito do desafio. A janela impede o prompt de crescer sem limite. *Rejeitado:* histórico integral no prompt (cresce indefinidamente e dilui o contexto relevante).
- **OQ-6 — Transporte do streaming.** **RESOLVIDO (2026-08-17):** SSE sobre `POST`, consumido no cliente por `fetch` + `ReadableStream`. *Justificativa:* o fluxo é unidirecional (servidor → cliente); WebSocket traria bidirecionalidade que ninguém usa, mais estado de conexão para gerenciar. O `nginx.conf` já foi escrito com `proxy_buffering off` para isso. *Rejeitado:* WebSocket e resposta única sem streaming (pior UX, e o desafio avalia experiência). *Nota:* `EventSource` foi descartado por não suportar `POST` nem headers customizados — daí o parsing manual do stream na `B.2`.
- **OQ-10 — Valor inicial de `SIMILARITY_THRESHOLD`.** **ABERTA.** O valor depende da escala de similaridade do modelo de embedding escolhido, que só se conhece com dados reais. Plano: começar permissivo, rodar `make eval` (`A.6`) e calibrar com base no `recall@k` medido e na taxa de recusa observada. Fica registrado em `.env.example` com o valor calibrado e a justificativa. Como é env, ajustar não exige mudança de código.

## 9. Definition of Done (gate por etapa)

**Gate por fase** — cada uma só fecha com seu critério de conclusão verde:

- [ ] `A.1 conversation-schema` — round-trip de conversa e mensagens com citações preservadas.
- [ ] `A.2 query-condensation` — pronome resolvido e pergunta autocontida preservada, offline.
- [ ] `A.3 retrieval` — isolamento por documento, top-k ordenado, limiar aplicado.
- [ ] `A.4 prompt-assembly` — prompt determinístico com trechos, páginas e instrução de fundamentação.
- [ ] `A.5 chat-endpoint` — pergunta real responde em streaming com citação de página correta.
- [ ] `A.6 rag-eval` — `make eval` reporta `recall@k` ≥ 0,8.
- [ ] `A.7 chat-tests` — suíte de integração verde sem `GEMINI_API_KEY`.
- [ ] `B.1 chat-view` — tela navegável com histórico mockado.
- [ ] `B.2 streaming` — resposta real renderizada token a token.
- [ ] `B.3 citations` — citações reais exibidas e expansíveis.
- [ ] `B.4 chat-errors` — cada código de erro exibe mensagem acionável; recusa distinta de falha.

**Itens globais transversais:**

- [ ] Cada FR desta spec tem ao menos um AC verificado.
- [ ] `make lint`, `make typecheck` e `make test` retornam zero.
- [ ] `make eval` roda e reporta a métrica (fora de `make check`, por consumir quota real).
- [ ] Nenhum módulo de `backend/app/core/` importa `fastapi`, `asyncpg` ou `google.genai` (princípio 1).
- [ ] Nenhuma dependência de framework de RAG foi adicionada (princípio 2).
- [ ] Toda resposta traz citações estruturadas em campo próprio do payload (princípio 3).
- [ ] Sem chunk acima do limiar, a API recusa e **não** chama o LLM (princípio 4).
- [ ] Nenhuma chave de API aparece em log, resposta ou evento SSE (princípio 5).
- [ ] Todo SQL é parametrizado e filtra por `document_id` e sessão (princípios 6 e 7).
- [ ] Identificadores em inglês; textos de UI e mensagens de erro em pt-BR (princípio 8).
- [ ] A suíte roda offline, sem chave de API (princípio 9).
- [ ] `.env.example` documenta toda variável nova, com o `SIMILARITY_THRESHOLD` calibrado.
- [ ] Nenhuma regressão em `FEAT-0001`: upload e ingestão seguem funcionando.
