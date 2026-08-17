---
id: FEAT-0002
slug: 02-chat-rag
title: "Chat conversacional com RAG: condensação, retrieval com limiar, citações, streaming e eval"
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
blocks: []
quality_gate:
  scorer: phase-evaluator
  threshold: 8.5
---

# FEAT-0002 — Chat com RAG

> **Nota de planning (2026-08-17, revisada):** reescrita após revisão adversarial por cinco revisores. Mudanças materiais: o frontend passa a ser dono da criação da conversa (antes ninguém era, e o chat não tinha como começar); o protocolo do cliente de chat inclui a chamada **não-streaming** que a condensação exige (antes não existia em spec nenhuma); o eval ganha perguntas negativas (sem elas a calibração do limiar era circular); e esta spec incorpora a persistência em `localStorage` que justificava a `FEAT-0003`, cortada. Registro em `.codeflow/decisions/2026-08-17-revisao-adversarial-das-specs.md`.
>
> **Pré-requisito externo:** `FEAT-0001` concluída — **Track A até `A.4`** para o backend desta spec, **Track B até `B.3`** para o frontend. Não basta o backend: as fases de frontend daqui alteram `lib/errors.ts`, `lib/api.ts` e `App.tsx`, criados lá.
>
> **Fora do escopo:** upload e ingestão (`FEAT-0001`); biblioteca de múltiplos documentos e exclusão (cortadas); busca cross-documento; autenticação e autorização por sessão; re-ranking com modelo dedicado; observabilidade.

## Resumo executivo (TL;DR)

| | |
|---|---|
| **O quê** | A pessoa conversa com o documento processado: pergunta, recebe resposta em streaming fundamentada nos trechos recuperados, com citação de página, e o chat entende perguntas de continuação. |
| **Por quê** | É o requisito 2 do desafio e o eixo mais pesado da avaliação: chunking, embeddings, retrieval, montagem de prompt e fundamentação. |
| **Backend-Infra** | Tabelas de conversa e mensagem; condensação com heurística e fallback determinístico; busca por cosseno com limiar; SSE nativo do FastAPI; eval com métricas que podem falhar. |
| **Frontend** | Criação da conversa, render incremental do streaming, chips de citação com página e trecho, erros por código, e retomada após recarregar. |
| **Decisão** | Abaixo do limiar o sistema recusa **sem chamar o LLM**; erro antes do primeiro evento é HTTP, depois dele é evento SSE; a resposta é persistida em `finally`, com marca de truncada. |
| **Tamanho** | L — 7 fases no Track A (backend) e 5 no Track B (frontend), a última delas o README e a demonstração. |

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

Dois detalhes do enunciado carregam a maior parte da dificuldade.

**"Compreender perguntas de continuação."** Quando alguém pergunta *"e quanto a isso?"* logo depois de *"quais serviços a YAITEC oferece?"*, buscar por *"e quanto a isso?"* no índice vetorial não recupera nada — o pronome não carrega semântica. A pergunta precisa ser condensada numa query autocontida **antes** do retrieval. Sem esse passo, a memória existe no prompt e não existe na busca, e o sistema falha exatamente onde o enunciado cobra.

**"Respostas fundamentadas, citando o trecho ou a página."** Fundamentar não é instruir o modelo a citar; é decidir o que fazer quando o documento não tem a resposta. Por isso o limiar e a recusa são requisitos, não refinamento — e por isso o eval precisa de perguntas que **devem** ser recusadas, senão a calibração do limiar não tem contrapeso e converge para zero.

**Onde a quota aperta muda de lugar.** Embeddings de query são baratos; quem estrangula é o chat, com ~10 RPM. E a condensação dobra o consumo por turno se disparar sempre — daí a heurística que só condensa quando a pergunta parece dependente de contexto.

O `frontend/nginx.conf` já foi escrito com `proxy_buffering off` e `proxy_read_timeout 300s` pensando neste streaming, e a barra sobrando no `proxy_pass` já foi corrigida.

### 1.1 Princípios invioláveis

Itens 1–5 de `.codeflow/constitution.md`, versionada neste repositório; itens 6–8 das rules universais do framework do autor.

1. **`backend/app/core/` não importa `fastapi`, `asyncpg` nem `google.genai`.** Aqui vale para condensação, seleção de top-k e montagem de prompt — os três puros e testáveis offline.
2. **Frameworks de RAG são proibidos.** O pipeline é escrito no projeto.
3. **Toda resposta traz citações estruturadas com página e trecho, em campo próprio do payload** — não embutidas no texto gerado.
4. **Sem chunk acima do limiar, a API recusa explicitamente em vez de gerar** — e não chama o LLM.
5. **`mypy --strict` e `tsc` strict zerados, sem afrouxar gate.**
6. **Toda entrada externa validada no servidor.** — rule `security`.
7. **SQL parametrizado.** — rule `security`.
8. **Identificadores em inglês, textos ao usuário em pt-BR; todo código novo com teste determinístico.** — rules `naming` e `testing`.

## 2. Requisitos

### Funcionais

- **FR-1** — `POST /api/conversations` cria uma conversa vinculada a um `document_id`. Documento que não esteja `ready` é recusado com `409` e `code: "documento_nao_pronto"`.
- **FR-2** — `POST /api/conversations/{id}/messages` recebe `{"question": "..."}` e responde por SSE, emitindo os tokens incrementalmente.
- **FR-3** — A pergunta é condensada numa query autocontida **apenas quando parece depender de contexto**: há histórico **e** a pergunta é curta (< 12 palavras) ou contém marcador anafórico (`isso, isto, esse, essa, ele, ela, lá, e quanto a, e sobre, detalhe mais, por quê, quais deles`). Pergunta autocontida vai direto ao retrieval.
- **FR-4** — Se a condensação falhar ou estourar `CONDENSE_TIMEOUT_SECONDS`, a query de retrieval passa a ser a concatenação da última pergunta do usuário com a atual — fallback determinístico, sem custo e sem erro visível.
- **FR-5** — O retrieval busca por similaridade de cosseno no pgvector, **sempre filtrando por `document_id`**, e devolve os `RETRIEVAL_TOP_K` melhores chunks com score em `[0,1]`.
- **FR-6** — Chunks abaixo de `SIMILARITY_THRESHOLD` são descartados. Se nenhum sobrevive, a API responde a recusa padrão em pt-BR com citações vazias e **não chama o LLM**.
- **FR-7** — O prompt reúne os chunks sobreviventes rotulados por página, a janela de histórico e a instrução de responder apenas com base no contexto.
- **FR-8** — Ao fim do streaming, um evento `citations` traz a lista de `{page_number, snippet, chunk_index, score}` dos chunks usados. O `snippet` tem no máximo 240 caracteres, recortado em fronteira de palavra **no servidor**.
- **FR-9** — A pergunta é persistida **antes** da chamada ao LLM; a resposta é persistida num `finally`, com campo `truncated` quando o stream não completou.
- **FR-10** — `GET /api/conversations/{id}/messages` devolve o histórico com as citações presas às respostas.
- **FR-11** — Erro **antes** do primeiro evento SSE é resposta HTTP normal com o envelope `{code, message}` da `FEAT-0001`. Erro **depois** do primeiro evento é evento SSE `error` com o mesmo vocabulário de `code`, seguido de fechamento limpo.
- **FR-12** — Desconexão do cliente encerra o gerador: o laço checa `request.is_disconnected()` a cada evento e o iterador do provedor é fechado, sem seguir consumindo quota.
- **FR-13** — Existe um eval de retrieval versionado, rodável por `make eval`, que reporta `recall@1`, `recall@3`, `MRR`, **taxa de recusa correta** nas perguntas negativas, **taxa de falsa recusa** nas positivas, e a distribuição de similaridade (mín/média/máx) separada por grupo.
- **FR-14** — A UI cria a conversa ao entrar no chat com um documento `ready` sem conversa ativa, e guarda o id.
- **FR-15** — A UI renderiza a resposta incrementalmente, mostra "pensando" entre o envio e o primeiro token, e permite cancelar via `AbortController`.
- **FR-16** — Cada resposta exibe suas citações como elementos focáveis que revelam trecho e página.
- **FR-17** — A recusa por falta de fundamento é exibida como resposta legítima do assistente, visualmente distinta de erro técnico.
- **FR-18** — `documentId` e `conversationId` vivem em `localStorage`; ao recarregar, a UI restaura o documento e o histórico da conversa.
- **FR-19** — O README documenta arquitetura, decisões (com alternativas rejeitadas), limitações conhecidas, ferramentas de IA usadas e um exemplo de uso reproduzível, e traz uma demonstração gravada.

### Não-funcionais

- **NFR-1** — O primeiro token chega em ≤ 5 s em condições normais de free tier, com `thinking_budget=0` no modelo de chat.
- **NFR-2** — Condensação, seleção de top-k, fusão e montagem de prompt vivem em `backend/app/core/` e são testáveis sem rede e sem banco.
- **NFR-3** — Nenhuma chave aparece em log, resposta ou evento SSE.
- **NFR-4** — `make lint`, `make typecheck` e `make test` zero, com `make test` offline (sem chave, sem banco).
- **NFR-5** — A janela de histórico é limitada por `HISTORY_WINDOW`, para o prompt não crescer com a conversa.
- **NFR-6** — `RETRIEVAL_TOP_K`, `SIMILARITY_THRESHOLD`, `HISTORY_WINDOW`, timeouts e ids de modelo são configuráveis por env.
- **NFR-7** — Com a configuração final, o eval atinge `recall@3 ≥ 0,8`, `MRR ≥ 0,7`, recusa correta em **todas** as perguntas negativas e falsa recusa igual a zero.

## 3. Critérios de aceite

- **AC-1** (FR-1) — *Dado* um documento em `processing`, *quando* tento criar conversa, *então* recebo `409` com `code: "documento_nao_pronto"`.
- **AC-2** (FR-2, FR-15) — *Dado* uma conversa válida, *quando* envio uma pergunta, *então* recebo eventos `token` que concatenados formam a resposta, e a UI a renderiza incrementalmente.
- **AC-3** (FR-3) — *Dado* `should_condense`, *então* ele é verdadeiro para "e quanto a isso?" com histórico e falso para "qual o endereço da empresa?" e falso sem histórico — determinístico, sem LLM.
- **AC-4** (FR-3) — *Dado* histórico e uma pergunta dependente, *quando* o prompt de condensação é montado, *então* ele contém a última pergunta do usuário e a instrução de devolver **apenas** a pergunta reescrita.
- **AC-5** (FR-4) — *Dado* que a condensação estoura o timeout, *quando* o pipeline segue, *então* a query de retrieval é a concatenação da pergunta anterior com a atual, e nenhum erro é exibido ao usuário.
- **AC-6** (FR-5) — *Dado* dois documentos ingeridos, *quando* pergunto na conversa do documento A, *então* nenhum chunk do documento B aparece nas citações.
- **AC-7** (FR-5) — *Dado* `RETRIEVAL_TOP_K=5`, *então* no máximo 5 chunks são considerados, ordenados por score decrescente, com score em `[0,1]`.
- **AC-8** (FR-6) — *Dado* uma pergunta sem relação com o documento, *quando* nada passa do limiar, *então* a resposta é a recusa padrão, as citações vêm vazias e **nenhuma chamada ao LLM é feita**.
- **AC-9** (FR-7, NFR-5) — *Dado* três chunks recuperados e uma conversa de 20 mensagens com `HISTORY_WINDOW=6`, *quando* o prompt é montado, *então* ele contém os três trechos com suas páginas, a instrução de fundamentação e no máximo as 6 últimas mensagens.
- **AC-10** (FR-8) — *Dado* uma resposta fundamentada, *quando* o streaming termina, *então* chega o evento `citations` com `page_number`, `snippet` (≤ 240 chars, sem cortar palavra), `chunk_index` e `score`.
- **AC-11** (FR-9, FR-10) — *Dado* uma conversa com três trocas, *quando* consulto o histórico, *então* recebo as seis mensagens na ordem, com citações nas respostas; *dado* um stream interrompido, *então* a resposta parcial é persistida com `truncated = true`.
- **AC-12** (FR-11) — *Dado* um `429` **antes** do primeiro evento, *então* recebo HTTP `429` com `{code:"limite_de_uso", message}`; *dado* um `429` **depois**, *então* recebo evento `error` com o mesmo `code` e a conexão fecha limpa.
- **AC-13** (FR-12) — *Dado* que aborto o stream no meio, *então* o gerador encerra e nenhum token adicional é consumido do provedor.
- **AC-14** (FR-13, NFR-7) — *Dado* o dataset versionado, *quando* rodo `make eval`, *então* o relatório traz `recall@1`, `recall@3`, `MRR`, recusa correta, falsa recusa e a distribuição de similaridade por grupo, e falha com saída não-zero abaixo dos limiares de NFR-7.
- **AC-15** (FR-14) — *Dado* um documento `ready` sem conversa ativa, *quando* entro no chat, *então* a UI cria a conversa e o campo de pergunta fica utilizável.
- **AC-16** (FR-15) — *Dado* que enviei uma pergunta, *então* vejo "pensando" até o primeiro token; ao cancelar, o streaming para e a UI volta ao estado utilizável.
- **AC-17** (FR-16) — *Dado* uma resposta com duas citações, *quando* foco ou clico numa delas, *então* vejo o trecho e a página.
- **AC-18** (FR-17) — *Dado* uma recusa por falta de fundamento, *então* ela aparece como resposta do assistente, sem banner de erro e sem área de citações vazia.
- **AC-19** (FR-18) — *Dado* uma conversa em andamento, *quando* recarrego a página, *então* documento e histórico são restaurados.
- **AC-20** (NFR-3, NFR-4) — *Dado* nenhuma `GEMINI_API_KEY` e nenhum banco, *quando* rodo `make test`, *então* a suíte passa inteira e nenhum log contém chave.
- **AC-21** (FR-19) — *Dado* o README entregue, *então* ele contém a tabela de decisões com alternativas rejeitadas, as limitações conhecidas, a seção de ferramentas de IA, o exemplo de uso reproduzível e o link da demonstração.

## 4. Abordagem técnica

### Pipeline de uma pergunta

```
pergunta + histórico
  → should_condense?  ── não ──────────────────────────┐
        │ sim                                          │
        ↓                                              │
   generate(prompt de condensação)  ──falha/timeout──→ fallback: pergunta anterior + atual
        ↓                                              │
        └──────────────→ query autocontida ←───────────┘
                              ↓
                    embed_query (FEAT-0001 A.3)
                              ↓
          busca por cosseno filtrada por document_id (SQL parametrizado)
                              ↓
              filtro por SIMILARITY_THRESHOLD + top-k   (core, puro)
                              ↓
          nenhum sobrevivente? → recusa em pt-BR, SEM chamar o LLM
                              ↓
                 montagem de prompt   (core, puro)
                              ↓
         stream_answer → eventos `token` → evento `citations` → `done`
                              ↓
              persistência em finally (truncated se incompleto)
```

Os três passos marcados `core` são puros: recebem dados, devolvem dados, não tocam rede nem banco. É o que sustenta o princípio 1 e o que torna o núcleo avaliado testável offline.

### Protocolos (contratos dos adapters)

`EmbeddingClient` já existe desde `FEAT-0001 A.3`, com `embed_documents` e `embed_query` **implementados e testados lá** — esta spec **consome**, não reimplementa.

Novo aqui:

```python
class ChatClient(Protocol):
    async def generate(self, prompt: str, *, timeout: float) -> str: ...
    def stream_answer(self, prompt: str) -> AsyncIterator[str]: ...
```

`generate` é a chamada única que a condensação usa; `stream_answer` é a geração incremental. Sem esse protocolo nomeado, o fake dos testes não teria interface para implementar. Ambos passam `thinking_budget=0`, `temperature=0.2` e `max_output_tokens`. O `chunk.text` do SDK pode vir `None` — filtrar antes de emitir o evento.

### Protocolo SSE

Servido por `fastapi.sse.EventSourceResponse` (FastAPI ≥ 0.135; resolvido 0.141.1, verificado), que já define `Content-Type`, `Cache-Control: no-cache`, `X-Accel-Buffering: no` e keep-alive de 15 s.

| Evento | Payload |
|---|---|
| `token` | `{"text": "..."}` |
| `citations` | `{"citations": [{"page_number", "snippet", "chunk_index", "score"}]}` |
| `error` | `{"code": "limite_de_uso\|provedor\|erro_interno", "message": "<pt-BR>"}` |
| `done` | `{"message_id": <int>, "truncated": <bool>}` |

`message_id` é inteiro, coerente com `messages(id bigserial)`.

**Regra de erro (FR-11):** antes do primeiro evento → HTTP normal com o envelope da `FEAT-0001`. Depois → evento `error`. O cliente checa `response.ok` e `Content-Type` **antes** de entrar no parser de stream.

### Contrato de API acrescentado

```
POST /api/conversations                   {"document_id": "<uuid>"} → 201 {"id": "<uuid>"}
POST /api/conversations/{id}/messages     {"question": "..."}       → SSE
GET  /api/conversations/{id}/messages                               → 200 [{"id","role","content","citations","created_at"}]
```

### Modelo de dados

```sql
conversations(id uuid pk default gen_random_uuid(),
              document_id uuid references documents(id) on delete cascade,
              session_id text, created_at timestamptz default now())
messages(id bigserial pk,
         conversation_id uuid references conversations(id) on delete cascade,
         role text, content text, citations jsonb, truncated bool default false,
         created_at timestamptz default now())
```

Cascades declaradas por quem cria as tabelas. `citations` como `jsonb`: é fato daquela resposta, não entidade com vida própria.

### Mapa NOVO vs. REUSADO vs. REMOVIDO

**REUSADO** (criado pela `FEAT-0001`; consumido ou estendido, nunca duplicado): `adapters/gemini.py` (ganha `ChatClient`; o backoff e a normalização já existem), `adapters/repository.py` (ganha os métodos de conversa e a busca vetorial), `adapters/db.py`, `core/models.py`, `config.py`, `main.py`, `errors.py` (o vocabulário de `code` é o mesmo), `db/`, `frontend/src/lib/{api,session,types,errors,config}.ts`, `frontend/src/App.tsx`, `frontend/nginx.conf`, `Makefile` (o alvo `eval` já existe).

**NOVO:** `db/002_conversations.sql`; `backend/app/core/{condensation,retrieval,prompt}.py`; `backend/app/{chat.py,api/conversations.py}`; `backend/eval/{dataset.json,run_eval.py,README.md}`; `backend/tests/test_{condensation,retrieval,prompt,chat_api}.py`; `frontend/src/components/{ChatView,MessageList,MessageInput,CitationChip}.tsx`; `frontend/src/hooks/useChat.ts`; `frontend/src/lib/sse.ts`; `README.md` (preenchido).

**REMOVIDO:** nada.

### Restrições de free tier e como o desenho responde

| Restrição | Efeito | Resposta |
|---|---|---|
| Chat ~10 RPM | rajada bate `429` | evento/HTTP de erro com mensagem clara e ação de repetir |
| Condensação gasta chamada extra | dobraria o consumo por turno | heurística de FR-3 corta a maioria dos turnos; fallback de FR-4 não custa nada |
| Recusa abaixo do limiar | — | economiza a chamada de geração (FR-6) |
| Chat ~250k TPM | histórico inflaria o prompt | `HISTORY_WINDOW` (NFR-5) |
| `thinking` ligado por default | latência antes do primeiro token | `thinking_budget=0` (NFR-1) |

## 5. Plano de desenvolvimento por fases

> Executável isoladamente por um agente lendo só este documento. **Pré-requisito externo:** `FEAT-0001` Track A até `A.4` (para o Track A daqui) e Track B até `B.3` (para o Track B daqui).

### Track A — Backend

### Fase A.1 — Schema e repositório de conversas *(tamanho S)*

- **id:** `A.1`
- **slug:** `conversation-schema`
- **Objetivo:** persistir conversas e mensagens, com cascade declarado na origem.
- **Depende de:** nenhuma
- **Arquivos novos:** `db/002_conversations.sql`, `backend/tests/test_conversation_repository.py`. **Arquivos alterados:** `backend/app/adapters/repository.py`, `backend/app/core/models.py`.
- **Passos:** 1) `002_conversations.sql` com as tabelas de §4, `ON DELETE CASCADE` e índices por `document_id` e `(conversation_id, created_at)`; 2) acrescentar ao repositório, com SQL parametrizado: criar conversa, buscar conversa, inserir mensagem, listar mensagens ordenadas; 3) `Message`, `Citation` e `RetrievedChunk` em `core/models.py` como dataclasses puras; 4) serializar citações em `jsonb` e desserializar na leitura.
- **Testes:** round-trip preservando ordem e citações (AC-11); mensagem com `truncated` persiste a flag.
- **Escopo travado / violações BLOQUEANTES:** sem ORM; sem SQL concatenado; `core/models.py` não importa `asyncpg`; não implementar rota aqui.
- **Critério de conclusão (gate):** `make down && make up` aplica `001` e `002` em ordem; testes verdes; `make lint typecheck test` zero.

### Fase A.2 — Núcleo de prompting: condensação e montagem *(tamanho M)*

- **id:** `A.2`
- **slug:** `core-prompting`
- **Objetivo:** decidir quando condensar, montar o prompt de condensação e montar o prompt de resposta — tudo puro.
- **Depende de:** nenhuma
- **Arquivos novos:** `backend/app/core/condensation.py`, `backend/app/core/prompt.py`, `backend/tests/test_condensation.py`, `backend/tests/test_prompt.py`. **Arquivos alterados:** nenhum.
- **Passos:** 1) `should_condense(history, question) -> bool` com a heurística de FR-3 (histórico presente **e** pergunta curta ou com marcador anafórico), determinística e sem LLM; 2) `select_history_window(messages, window)`; 3) `build_condensation_prompt(history, question)` instruindo a devolver **só** a pergunta reescrita, em pt-BR; 4) `fallback_query(history, question)` concatenando a última pergunta do usuário com a atual (FR-4); 5) `build_answer_prompt(chunks, history, question)` com cada trecho delimitado e rotulado por página, a instrução de responder apenas com base no contexto, e a janela de histórico; 6) constante da mensagem de recusa em pt-BR.
- **Testes:** `should_condense` verdadeiro/falso nos casos de AC-3; prompt de condensação com a última pergunta e a instrução (AC-4); prompt de resposta com trechos, páginas e janela (AC-9); determinismo para a mesma entrada.
- **Escopo travado / violações BLOQUEANTES:** módulos puros — sem rede, sem banco, sem `fastapi`; não chamar LLM aqui (quem chama é o orquestrador da `A.4`); não delimitar mal o bloco de contexto (conteúdo do usuário precisa de fronteira clara).
- **Critério de conclusão (gate):** testes verdes sem rede; `make lint typecheck test` zero.

### Fase A.3 — Retrieval com limiar *(tamanho M)*

- **id:** `A.3`
- **slug:** `retrieval`
- **Objetivo:** recuperar os chunks mais relevantes do documento da conversa e descartar o que não sustenta resposta.
- **Depende de:** `A.1`
- **Arquivos novos:** `backend/app/core/retrieval.py`, `backend/tests/test_retrieval.py`. **Arquivos alterados:** `backend/app/adapters/repository.py`, `backend/app/config.py`.
- **Passos:** 1) busca vetorial no repositório com SQL parametrizado: `ORDER BY embedding <=> $1::vector`, **filtrando por `document_id`**, `LIMIT` de `RETRIEVAL_TOP_K`; 2) converter distância em score `1 - distance`, em `[0,1]`, com 3 casas; 3) em `core/retrieval.py`, puro: filtrar por `SIMILARITY_THRESHOLD`, ordenar e cortar em top-k; 4) `has_grounding(chunks) -> bool`; 5) `build_snippet(content) -> str` recortando em 240 caracteres na fronteira de palavra.
- **Testes:** isolamento por documento (AC-6); top-k ordenado com score em `[0,1]` (AC-7); tudo abaixo do limiar resulta em lista vazia e `has_grounding` falso (AC-8); snippet nunca corta palavra (AC-10).
- **Escopo travado / violações BLOQUEANTES:** o filtro por `document_id` não é opcional; `core/retrieval.py` não toca banco; nenhum SQL concatenado; usar o operador `<=>` (cosseno), coerente com o índice `vector_cosine_ops` criado na `FEAT-0001`.
- **Critério de conclusão (gate):** testes verdes; busca real devolve chunks do documento certo; `make lint typecheck test` zero.

### Fase A.4 — Endpoint de chat com streaming *(tamanho L)*

- **id:** `A.4`
- **slug:** `chat-endpoint`
- **Objetivo:** amarrar o pipeline numa rota SSE que responde incrementalmente, persiste com honestidade e falha com clareza.
- **Depende de:** `A.1`, `A.2`, `A.3`
- **Arquivos novos:** `backend/app/api/conversations.py`, `backend/app/chat.py`. **Arquivos alterados:** `backend/app/main.py`, `backend/app/adapters/gemini.py`, `backend/app/api/schemas.py`, `backend/app/config.py`.
- **Passos:**
  1. Implementar `ChatClient` (§4) em `gemini.py`: `generate` e `stream_answer`, reusando o backoff existente, com `thinking_budget=0`, `temperature=0.2` e `max_output_tokens`; filtrar `chunk.text` nulo.
  2. `POST /api/conversations` validando que o documento está `ready` (`409` com `code: "documento_nao_pronto"`).
  3. `POST /api/conversations/{id}/messages` com `EventSourceResponse`.
  4. Orquestrar em `chat.py`: persistir a pergunta **antes** de tudo → condensar se `should_condense`, com timeout próprio e fallback de FR-4 → `embed_query` → buscar → filtrar → **se sem fundamento, emitir a recusa e encerrar sem chamar o LLM** → montar prompt → `stream_answer`.
  5. Emitir `citations` e depois `done`; persistir a resposta num `finally`, com `truncated` quando o stream não completou.
  6. Checar `request.is_disconnected()` a cada evento; tratar `asyncio.CancelledError` fechando o iterador do provedor.
  7. Mapear erro do provedor: **antes** do primeiro evento → HTTP com o envelope; **depois** → evento `error`.
  8. `GET /api/conversations/{id}/messages`.
- **Testes:** streaming concatenado (AC-2); fallback de condensação (AC-5); recusa sem chamar LLM (AC-8); evento de citações completo (AC-10); histórico e `truncated` (AC-11); erro pré e mid-stream (AC-12); desconexão encerra o gerador (AC-13); documento não-`ready` (AC-1).
- **Escopo travado / violações BLOQUEANTES:** nenhuma chamada ao Gemini fora do adapter; **não bufferizar a resposta inteira** antes de emitir; não persistir resposta parcial como completa; **não adicionar `GZipMiddleware`** (quebra SSE); não reimplementar `embed_query`, que já existe desde `FEAT-0001 A.3`.
- **Critério de conclusão (gate):** pergunta real sobre o `Exemplo-YAITEC.pdf` responde em streaming **através do `docker compose`** com citação de página correta; `make lint typecheck test` zero.

### Fase A.5 — Eval de retrieval *(tamanho M)*

- **id:** `A.5`
- **slug:** `rag-eval`
- **Objetivo:** **medir** a qualidade do retrieval com métricas que podem falhar, e calibrar o limiar com dado em vez de palpite.
- **Depende de:** `A.3`
- **Arquivos novos:** `backend/eval/{dataset.json,run_eval.py,README.md}`. **Arquivos alterados:** nenhum — o alvo `eval` já existe no `Makefile`.
- **Passos:**
  1. `dataset.json` com 8–12 perguntas **positivas** (com `expected_page`) sobre o `Exemplo-YAITEC.pdf` e **4 negativas** com `expected_page: null` — perguntas comprovadamente fora do documento. Incluir ao menos uma **pergunta de continuação** cuja página só é alcançável se a condensação funcionar.
  2. `run_eval.py` roda o retrieval de cada item contra um `document_id` já ingerido (parâmetro), **sem reingerir a cada execução** — a calibração exige rodar várias vezes e reingerir queimaria quota.
  3. Reportar `recall@1`, `recall@3`, `MRR` nas positivas; taxa de recusa correta nas negativas; taxa de falsa recusa nas positivas; e a distribuição de similaridade (mín/média/máx) **separada por grupo** — é esse contraste que escolhe o limiar.
  4. Saída não-zero quando abaixo dos limiares de NFR-7.
  5. `backend/eval/README.md` explicando o que é medido, como interpretar a distribuição, o valor calibrado de `SIMILARITY_THRESHOLD` e o resultado da verificação de lote de embeddings feita na `FEAT-0001 A.3`.
  6. Registrar o valor calibrado no `.env.example`.
- **Testes:** `make eval` roda e reporta as seis métricas (AC-14); falha com saída não-zero abaixo do limiar.
- **Escopo travado / violações BLOQUEANTES:** o eval **não** entra em `make check` (consome quota real); não commitar chave no dataset; **não ajustar o dataset para inflar a métrica**; não otimizar o limiar só por recall — sem o contrapeso da falsa recusa a calibração converge para zero.
- **Critério de conclusão (gate):** `make eval` atinge NFR-7 e o `backend/eval/README.md` justifica o limiar com a distribuição medida; `make lint typecheck` zero.

### Fase A.6 — Testes de integração do chat *(tamanho M)*

- **id:** `A.6`
- **slug:** `chat-tests`
- **Objetivo:** provar o comportamento do chat com fakes, offline e determinístico.
- **Depende de:** `A.4`
- **Arquivos novos:** `backend/tests/test_chat_api.py`. **Arquivos alterados:** `backend/tests/{fakes,conftest}.py`.
- **Passos:** 1) estender os fakes da `FEAT-0001 A.5` com um `FakeChatClient` implementando `ChatClient` (streaming determinístico, condensação previsível, e modo que levanta `429` antes ou depois do primeiro token); 2) testar criar conversa → perguntar → tokens → citações → histórico; 3) testar a recusa verificando que o `FakeChatClient` **não** foi chamado; 4) testar a pergunta de continuação verificando a query que chegou ao retrieval; 5) testar erro pré e mid-stream; 6) testar desconexão; 7) garantir suíte offline.
- **Testes:** AC-1, AC-2, AC-5, AC-8, AC-10, AC-11, AC-12, AC-13, AC-20.
- **Escopo travado / violações BLOQUEANTES:** nenhuma chamada de rede real; nenhum `skip` para mascarar flakiness; **não asserir sobre texto gerado por LLM real** (não-determinístico) — asserir sobre estrutura e sobre o que foi passado aos colaboradores.
- **Critério de conclusão (gate):** `make test` verde sem `GEMINI_API_KEY` e sem banco; `make lint typecheck` zero.

### Fase A.7 — Busca híbrida com fusão RRF *(tamanho M; opcional)*

- **id:** `A.7`
- **slug:** `hybrid-search`
- **Objetivo:** recuperar também por termo exato, fundindo com a busca densa — é o que resolve perguntas por e-mail, telefone e nome próprio, que o vetor borra.
- **Depende de:** `A.5`
- **Arquivos novos:** `backend/tests/test_rrf.py`. **Arquivos alterados:** `db/002_conversations.sql` (coluna gerada e índice GIN em `chunks`), `backend/app/adapters/repository.py`, `backend/app/core/retrieval.py`, `backend/eval/README.md`.
- **Passos:** 1) coluna `tsv tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', content)) STORED` em `chunks`, com índice GIN; 2) segunda query com `ts_rank_cd`, parametrizada, filtrada por `document_id`; 3) `reciprocal_rank_fusion(dense, lexical, k)` em `core/retrieval.py` — **puro, ~20 linhas, testável offline**; 4) o limiar continua sendo aplicado sobre o score denso do chunk fundido; 5) rodar `make eval` antes e depois e registrar o delta de `MRR` no `backend/eval/README.md`.
- **Testes:** RRF puro com listas conhecidas produz a ordenação esperada; documento com termo exato raro é recuperado pela via lexical e não pela densa.
- **Escopo travado / violações BLOQUEANTES:** a fusão vive em `core/`, sem tocar banco; não substituir a busca densa — fundir; **esta fase só começa se `A.1`–`A.6` e `B.1`–`B.4` estiverem fechadas**; se a mudança em `db/` exigir `make down`, avaliar se vale o custo àquela altura.
- **Critério de conclusão (gate):** `make eval` mostra o delta medido; `make lint typecheck test` zero.

### Track B — Frontend

### Fase B.1 — Tela de chat e criação da conversa *(tamanho M)*

- **id:** `B.1`
- **slug:** `chat-view`
- **Objetivo:** estrutura visual da conversa **e o passo que faz o chat existir**: criar a conversa.
- **Depende de:** `A.4`
- **Arquivos novos:** `frontend/src/components/{ChatView,MessageList,MessageInput}.tsx`. **Arquivos alterados:** `frontend/src/App.tsx`, `frontend/src/lib/{api,types}.ts`.
- **Passos:** 1) acrescentar a `api.ts` os métodos de criar conversa e ler histórico, e os tipos correspondentes em `types.ts`, derivados de §4; 2) **ao entrar no chat com um documento `ready` e sem conversa ativa, chamar `POST /api/conversations` e guardar o id** (FR-14) — sem este passo nada mais funciona; 3) layout com lista rolável e campo fixo; 4) diferenciar visualmente usuário e assistente; 5) desabilitar envio com entrada vazia ou resposta em andamento; 6) rolagem automática para a última mensagem, sem sequestrar o scroll quando o usuário subiu para ler.
- **Testes:** entrar no chat cria a conversa e habilita o campo (AC-15); lista renderiza histórico na ordem.
- **Escopo travado / violações BLOQUEANTES:** não instalar UI kit nem biblioteca de estado; textos em pt-BR e identificadores em inglês; não afrouxar `strict`; não criar conversa nova a cada render.
- **Critério de conclusão (gate):** conversa criada contra o backend real e campo utilizável; lint e typecheck zero.

### Fase B.2 — Streaming da resposta *(tamanho M)*

- **id:** `B.2`
- **slug:** `streaming`
- **Objetivo:** consumir o SSE e renderizar a resposta enquanto ela é gerada.
- **Depende de:** `B.1`
- **Arquivos novos:** `frontend/src/lib/sse.ts`, `frontend/src/hooks/useChat.ts`. **Arquivos alterados:** `frontend/src/components/ChatView.tsx`.
- **Passos:** 1) `sse.ts` consumindo via `fetch` + `ReadableStream` — `EventSource` não suporta `POST` nem headers — parseando os quatro eventos de §4; 2) **checar `response.ok` e `Content-Type` antes de entrar no parser**: erro pré-stream vem como JSON, não como `text/event-stream` (FR-11); 3) `useChat` acumulando tokens numa mensagem em construção; 4) prender as citações ao receber `citations`; 5) cancelamento por `AbortController`, limpo ao desmontar; 6) indicador de "pensando" até o primeiro token.
- **Testes:** tokens aparecem incrementalmente (AC-2); pensando e cancelamento (AC-16); erro pré-stream é tratado como JSON (AC-12).
- **Escopo travado / violações BLOQUEANTES:** não aguardar o stream inteiro para renderizar; não deixar `AbortController` órfão; não usar `EventSource`.
- **Critério de conclusão (gate):** resposta real renderiza token a token **através do `docker compose`**, não do dev server; lint e typecheck zero.

### Fase B.3 — Citações na interface *(tamanho S)*

- **id:** `B.3`
- **slug:** `citations`
- **Objetivo:** tornar a fundamentação visível e verificável.
- **Depende de:** `B.2`
- **Arquivos novos:** `frontend/src/components/CitationChip.tsx`. **Arquivos alterados:** `frontend/src/components/MessageList.tsx`.
- **Passos:** 1) renderizar sob cada resposta os chips rotulados com a página; 2) ao focar ou clicar, expandir o `snippet`; 3) ordenar por página; 4) resposta sem citação (recusa) não renderiza área vazia; 5) chip focável com rótulo descritivo.
- **Testes:** clique revela trecho e página (AC-17); resposta sem citação não exibe a área (AC-18).
- **Escopo travado / violações BLOQUEANTES:** não recortar o snippet no cliente (vem pronto do servidor, FR-8); **não fabricar citação** — renderizar só o que veio no evento.
- **Critério de conclusão (gate):** citações reais exibidas e expansíveis; lint e typecheck zero.

### Fase B.4 — Erros, recusa e persistência de sessão *(tamanho M)*

- **id:** `B.4`
- **slug:** `chat-errors-persistence`
- **Objetivo:** distinguir recusa legítima de falha técnica, e não perder o contexto ao recarregar.
- **Depende de:** `B.3`
- **Arquivos novos:** nenhum. **Arquivos alterados:** `frontend/src/lib/errors.ts`, `frontend/src/components/{ChatView,MessageList}.tsx`, `frontend/src/hooks/useChat.ts`.
- **Passos:** 1) estender `errors.ts` com os códigos desta spec (`limite_de_uso`, `provedor`, `erro_interno`, `documento_nao_pronto`), mantendo o mapeamento **por `code`**; 2) erro técnico vira banner com botão de repetir, **preservando a pergunta digitada**; 3) recusa por falta de fundamento renderiza como mensagem normal do assistente, com marcação sutil e sem aparência de erro (FR-17); 4) queda no meio do stream preserva o texto já recebido e marca a mensagem como interrompida; 5) **persistir `documentId` e `conversationId` em `localStorage`** e, no boot, restaurar documento e histórico via `GET /api/conversations/{id}/messages` (FR-18); 6) estado vazio da conversa com sugestão de primeira pergunta.
- **Testes:** `429` vira mensagem com ação (AC-12); recusa aparece como resposta, não erro (AC-18); recarregar restaura documento e histórico (AC-19).
- **Escopo travado / violações BLOQUEANTES:** nunca exibir stack trace, código de exceção ou chave; não perder a pergunta quando o envio falha; não usar `alert()`; não recriar conversa ao restaurar.
- **Critério de conclusão (gate):** cada código de erro reproduzido exibe a mensagem certa, e um `F5` no meio da conversa restaura tudo; lint e typecheck zero.

### Fase B.5 — README e demonstração *(tamanho M)*

- **id:** `B.5`
- **slug:** `readme-demo`
- **Objetivo:** entregar os artefatos que o enunciado nomeia e que o avaliador consome nos primeiros minutos.
- **Depende de:** `B.4`, `A.5`
- **Arquivos novos:** `scripts/demo.sh`, `docs/demo.gif` (ou link externo). **Arquivos alterados:** `README.md`, `.env.example`.
- **Passos:**
  1. README com: setup em três comandos e **aviso de que o primeiro build leva ~4 min**; diagrama do pipeline de §4; **tabela de decisões** (escolhi / por quê / rejeitei), recortada das Open Questions das duas specs, escrita com as próprias palavras; resultados do `make eval` colados (o avaliador não vai rodar); limitações conhecidas (`session_id` organiza mas não protege, sem OCR, sem autenticação, um documento por conversa); **seção de ferramentas de IA** dizendo quais, para quê, e o que foi revisado e mudado; parágrafo explicando que `.codeflow/` é o framework pessoal de planejamento do autor; e "Próximos passos" com a biblioteca de documentos que ficou fora e por quê.
  2. Exemplo de uso reproduzível: enviar o `Exemplo-YAITEC.pdf`, perguntar X, obter resposta citando a página Y.
  3. `scripts/demo.sh`: sobe o PDF por `curl`, espera `ready`, faz três perguntas e imprime resposta e citações — prova de vida, smoke test do clone limpo e plano B se a UI engasgar.
  4. Demonstração gravada de ~90 s com três cenas: upload com progresso real; pergunta respondida em streaming com o chip de citação aberto; **e uma pergunta que o documento não responde, mostrando a recusa** — essa é a cena mais forte e leva dez segundos.
  5. Ensaio de entrega: `git clone` numa pasta descartável, `docker compose up --build` cronometrado, conferir que sobe de primeira.
- **Testes:** `scripts/demo.sh` roda de ponta a ponta contra o compose e imprime resposta com citação (AC-21); o clone limpo sobe sem intervenção.
- **Escopo travado / violações BLOQUEANTES:** não deixar `<!-- TODO -->` no README entregue; **não colar resultado de eval que não foi medido**; não vazar chave no README nem no script; não prometer no README o que não foi implementado.
- **Critério de conclusão (gate):** README sem TODOs, com decisões, limitações, ferramentas de IA, resultados do eval e link da demo; ensaio de clone limpo executado com sucesso.

## 6. Riscos

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| 1 | `SIMILARITY_THRESHOLD` mal calibrado — recusa demais ou fundamenta de menos | Alta | Alto | `A.5` mede recusa correta **e** falsa recusa, com a distribuição por grupo; é env, ajustável sem redeploy |
| 2 | Condensação piorar perguntas autocontidas ou custar quota demais | Média | Médio | Heurística de FR-3 corta a maioria dos turnos; fallback de FR-4 cobre falha e timeout |
| 3 | Buffering matar o streaming | Baixa | Alto | `EventSourceResponse` já manda `X-Accel-Buffering: no`; `nginx.conf` tem `proxy_buffering off`; gates de `B.2` e `A.4` exigem validação **pelo compose** |
| 4 | `429` do chat durante a demonstração | Média | Médio | Mensagem clara com ação de repetir; e a demo gravada da `B.5` é o plano B |
| 5 | Contrato SSE divergir entre tracks | Baixa | Médio | Tabela de §4 é a fonte única; `B.2` depende de `A.4` |
| 6 | Resposta parcial persistida como completa | Baixa | Médio | Persistência em `finally` com `truncated` (FR-9) |
| 7 | `A.7` (híbrida) atrasar o essencial | Média | Médio | É opcional e só inicia com `A.1`–`A.6` e `B.1`–`B.4` fechadas |
| 8 | README e demo ficarem para os últimos 20 minutos | Alta | Alto | Viraram a fase `B.5`, com gate próprio — não são item de checklist |

## 7. Rollout

Sem produção e sem flag. `A.1`, `A.2` e `A.3` podem correr em paralelo (só `A.3` depende de `A.1`). `A.4` amarra e é onde o chat passa a existir. `A.5` depende só de `A.3` e **deve ser feita cedo** — é ela que troca o palpite do limiar por um número medido.

No Track B, `B.1` é o ponto de entrada e depende de `A.4`. `B.5` fecha a entrega.

Ponto de parada limpo: fim de `B.5`. A `A.7` é bônus e só entra com tudo fechado.

Rollback é `git revert` da fase. Mudança de schema exige `make down` antes do próximo `up`.

## 8. Open Questions

- **OQ-2 — Escopo do retrieval.** **RESOLVIDO (2026-08-17):** sempre filtrado pelo `document_id` da conversa. *Justificativa:* o desafio pede "conversa sobre o PDF", singular; filtrar deixa a citação inequívoca e a fundamentação limpa, e é o caminho de menos trabalho. *Rejeitado:* busca em toda a biblioteca e toggle híbrido.
- **OQ-3 — Memória da conversa.** **RESOLVIDO (2026-08-17):** janela de 6 mensagens mais condensação **condicional** da pergunta. *Justificativa:* sem condensar, a memória existe no prompt e não no retrieval, e perguntas de continuação não recuperam nada. A condicionalidade veio da revisão: "condensar só quando há histórico" não controla custo, porque sempre há histórico a partir da segunda pergunta. *Rejeitado:* histórico integral no prompt; e condensação incondicional, que dobraria o consumo num teto de ~10 RPM.
- **OQ-6 — Transporte do streaming.** **RESOLVIDO (2026-08-17):** SSE sobre `POST` com `fastapi.sse.EventSourceResponse`, consumido por `fetch` + `ReadableStream`. *Justificativa:* fluxo unidirecional; e a classe nativa entrega headers e keep-alive que a spec anterior teria de listar à mão. *Rejeitado:* `StreamingResponse` manual, WebSocket, resposta única. *Nota:* `EventSource` não suporta `POST` nem headers — daí o parsing manual no cliente.
- **OQ-10 — Valor de `SIMILARITY_THRESHOLD`.** **RESOLVIDO quanto ao método (2026-08-17); o número sai da `A.5`.** *Justificativa:* o plano anterior — "começar permissivo e calibrar pelo `recall@k`" — era circular, porque recall melhora monotonicamente quanto mais baixo o limiar, empurrando-o para zero e destruindo a recusa. O método correto é o contraste entre a distribuição de similaridade das perguntas positivas e das negativas, com falsa recusa como contrapeso. *Rejeitado:* calibrar só por recall. O valor calibrado e sua justificativa ficam em `.env.example` e `backend/eval/README.md`.
- **OQ-14 — Técnicas adicionais de RAG.** **RESOLVIDO (2026-08-17):** entra apenas a busca híbrida com fusão RRF, como fase opcional `A.7`. *Justificativa:* num corpus pequeno a busca densa borra termos exatos (e-mail, telefone, nome próprio), que é o que um avaliador pergunta; e a fusão é pura, ~20 linhas, testável offline, sustentando a alegação de RAG artesanal. *Rejeitado:* MMR e diversidade (no-op quando o top-k cobre boa parte do corpus); expansão multi-query (gasta chamada de LLM no teto que a condensação já estrangula); re-ranking com modelo dedicado (fora de escopo).

## 9. Definition of Done (gate por etapa)

**Gate por fase:**

- [ ] `A.1 conversation-schema` — round-trip com citações e `truncated`; cascades na origem.
- [ ] `A.2 core-prompting` — heurística e prompts determinísticos, offline.
- [ ] `A.3 retrieval` — isolamento por documento, top-k ordenado, limiar, snippet recortado.
- [ ] `A.4 chat-endpoint` — pergunta real responde em streaming pelo compose com citação correta.
- [ ] `A.5 rag-eval` — as seis métricas reportadas; NFR-7 atingido; limiar justificado pela distribuição.
- [ ] `A.6 chat-tests` — suíte verde sem chave e sem banco.
- [ ] `A.7 hybrid-search` *(opcional)* — delta de MRR medido e registrado.
- [ ] `B.1 chat-view` — conversa criada; campo utilizável.
- [ ] `B.2 streaming` — resposta renderizada token a token pelo compose.
- [ ] `B.3 citations` — citações exibidas e expansíveis.
- [ ] `B.4 chat-errors-persistence` — erros acionáveis, recusa distinta, `F5` restaura tudo.
- [ ] `B.5 readme-demo` — README completo, demo gravada, ensaio de clone limpo executado.

**Itens globais transversais:**

- [ ] Cada FR tem ao menos um AC verificado.
- [ ] `make lint`, `make typecheck` e `make test` zero, com `make test` offline.
- [ ] `make eval` roda e reporta (fora de `make check`).
- [ ] Nenhum módulo de `backend/app/core/` importa `fastapi`, `asyncpg` ou `google.genai`.
- [ ] Nenhuma dependência de framework de RAG.
- [ ] Toda resposta traz citações estruturadas em campo próprio.
- [ ] Sem chunk acima do limiar, a API recusa e não chama o LLM.
- [ ] Nenhuma chave em log, resposta ou evento SSE.
- [ ] Todo SQL parametrizado e filtrado por `document_id`.
- [ ] Identificadores em inglês; textos de UI em pt-BR.
- [ ] `.env.example` documenta toda variável nova, com o `SIMILARITY_THRESHOLD` calibrado.
- [ ] README sem `<!-- TODO -->`, com decisões, limitações, ferramentas de IA e resultados do eval.
- [ ] `ygorbalves` adicionado como colaborador do repositório privado.
- [ ] Nenhuma regressão em `FEAT-0001`: upload e ingestão seguem funcionando.
