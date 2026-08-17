---
id: FEAT-0001
slug: ingestao-pdf
title: "Ingestão de PDF: upload, extração, chunking, embeddings e vector store"
type: feature
status: draft
priority: P0
size: M
wave: multi
domain: fullstack
bounded_context: ingestion
cross_context: [rag]
created_at: 2026-08-17
updated_at: 2026-08-17
owner: gabriel
depends_on: []
blocks: [FEAT-0002, FEAT-0003]
quality_gate:
  scorer: phase-evaluator
  threshold: 8.5
---

# FEAT-0001 — Ingestão de PDF

> **Nota de planning (2026-08-17):** spec construída após sondagem do repositório, que hoje é o esqueleto gerado por `/bootstrap` (commit `7166d54`) — não há código de aplicação. Tudo que é lógica é **NOVO**; o que já existe e será **REUSADO** são os seams de infraestrutura (`db/` montado em `docker-entrypoint-initdb.d`, pacotes `backend/app/{core,adapters,api}/`, `Makefile`, `docker-compose.yml`, `.env.example`).
>
> **Fora do escopo desta spec:** o chat e todo o pipeline de retrieval/geração (vive em `FEAT-0002`); biblioteca de múltiplos documentos e persistência de conversas (`FEAT-0003`); autenticação; formatos além de PDF; OCR de PDF escaneado; deploy e CI; testes E2E de browser; observabilidade.

## Resumo executivo (TL;DR)

| | |
|---|---|
| **O quê** | Uma pessoa envia um PDF; o sistema extrai o texto por página, quebra em chunks, gera embeddings via Gemini, persiste no pgvector e expõe o estado do processamento. |
| **Por quê** | É o requisito 1 do desafio e a fundação de tudo: sem chunks embedados e citáveis por página, não existe RAG fundamentado nem citação. |
| **Backend-Infra** | Schema inicial (`documents`, `chunks`) com extensão `vector` e índice HNSW; config por env; upload multipart; `BackgroundTasks`; adapter Gemini com batch, backoff e pool opcional de chaves. |
| **Frontend** | Tela de upload com dropzone, validação client-side, barra de progresso, polling de estado e mensagens de erro em pt-BR. |
| **Decisão** | Processamento assíncrono com máquina de estados consultável por polling; limites calibrados para o free tier e configuráveis por env. |
| **Tamanho** | M — 6 fases no Track A (backend) e 4 no Track B (frontend). |

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

O desafio técnico da YAITEC pede um app onde a pessoa envia um PDF e conversa com ele, com respostas fundamentadas citando trecho ou página. Antes de qualquer conversa existir, o documento precisa virar dado consultável por similaridade: texto extraído, quebrado em pedaços de tamanho útil, convertido em vetores e guardado num índice.

O repositório hoje é o esqueleto do `/bootstrap`: os pacotes `backend/app/core/`, `backend/app/adapters/` e `backend/app/api/` existem e estão vazios; `db/` existe e está vazio; `docker-compose.yml` já declara os três serviços e monta `./db` em `docker-entrypoint-initdb.d`; `frontend/src/` existe e está vazio. **O seam central desta spec é o `db/`**: é por ele que o schema e a extensão `vector` entram sem nenhuma ferramenta de migração.

Esta é também a fase em que as restrições do free tier do Gemini deixam de ser teoria. O gargalo medido é o **TPM de embeddings (~30.000 tokens/min)** — não o número de requisições, que o batch resolve. Um documento no teto desta spec (50 páginas de texto denso, ~53k tokens) leva por volta de **1,8 minuto** só de embedding. Por isso o processamento é assíncrono e o estado é visível: o requisito "mostre ao usuário que está processando" não é enfeite, é consequência direta da quota.

### 1.1 Princípios invioláveis

1. **`backend/app/core/` não importa `fastapi`, `asyncpg` nem `google.genai`.** Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`. Consequência prática: chunking é testável sem rede e sem banco.
2. **Frameworks de RAG são proibidos** (`langchain`, `llama-index` e equivalentes não entram nas dependências). Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`.
3. **Segredos vivem apenas em variável de ambiente e nunca aparecem em log ou em mensagem de exceção.** Origem: `.codeflow/constitution.md` + rule universal `security` (`## Regras`, "Secrets fora do git"; `## Anti-regras`, "Não logar dados sensíveis").
4. **Toda entrada externa é validada no servidor antes de uso.** Origem: rule universal `security` (`## Regras`, "Validação de input"; `## Anti-regras`, "Não confiar em validação só do lado do cliente").
5. **SQL é parametrizado; nunca concatenação de string com input externo.** Origem: rule universal `security` (`## Anti-regras`).
6. **Identificadores de código em inglês; mensagens visíveis ao usuário em pt-BR.** Origem: rule universal `naming` (`## Regras`) + `.codeflow/constitution.md`.
7. **Todo código novo tem teste correspondente; teste descreve comportamento e é determinístico.** Origem: rule universal `testing` (`## Regras`).
8. **`mypy --strict` sobre `backend/app` e `tsc --noEmit` strict sobre `frontend/src` retornam zero; nenhum gate é afrouxado para fazer código passar.** Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas`.
9. **A partir de um clone limpo, `docker compose up --build` sobe a aplicação inteira.** Origem: `.codeflow/constitution.md`, `## Regras invariantes específicas` e `## Áreas de alto risco`.
10. **Funções pequenas e nomes expressivos; sem duplicação descontrolada.** Origem: rule universal `code-quality` (`## Regras`).

## 2. Requisitos

### Funcionais

- **FR-1** — `POST /api/documents` aceita upload multipart de um arquivo PDF e responde imediatamente com o `id` do documento e estado `pending`, sem aguardar o processamento.
- **FR-2** — O servidor valida o arquivo antes de aceitar: content-type e assinatura de PDF, tamanho ≤ `MAX_UPLOAD_MB`, número de páginas ≤ `MAX_PDF_PAGES`, texto extraído ≤ `MAX_EXTRACTED_CHARS`. Violação retorna `4xx` com mensagem em pt-BR identificando qual limite falhou.
- **FR-3** — PDF sem camada de texto extraível (tipicamente escaneado) é rejeitado com mensagem em pt-BR explicando que OCR não é suportado.
- **FR-4** — A extração produz o texto de cada página associado ao seu número de página (base 1).
- **FR-5** — O chunking é determinístico: janela de `CHUNK_SIZE` caracteres (default 1000) com `CHUNK_OVERLAP` (default 150), cortando preferencialmente em fronteira de parágrafo e, na falta dela, de sentença. Cada chunk carrega o número da página de origem e seu índice de ordem no documento.
- **FR-6** — Os embeddings são gerados via Gemini em lote (`batchEmbedContents`), com no máximo `EMBEDDING_BATCH_SIZE` textos por requisição, retry com backoff exponencial em erro transitório e `429`.
- **FR-7** — O adapter Gemini aceita uma chave (`GEMINI_API_KEY`) ou uma lista (`GEMINI_API_KEYS`, separada por vírgula), fazendo round-robin entre elas e trocando de chave ao receber `429`.
- **FR-8** — Documento e chunks são persistidos no Postgres; o vetor de cada chunk vive em coluna `vector` com índice HNSW.
- **FR-9** — O documento percorre a máquina de estados `pending → processing → ready → failed`. Falha registra uma mensagem de erro legível em pt-BR junto ao documento.
- **FR-10** — `GET /api/documents/{id}` devolve o estado atual, o total de chunks processados e o total esperado, permitindo progresso.
- **FR-11** — A tela de upload permite selecionar ou arrastar um PDF, valida tamanho e extensão no cliente antes de enviar, e exibe progresso de envio.
- **FR-12** — Após o envio, a UI faz polling de `GET /api/documents/{id}` e exibe o estado do processamento com indicação de progresso até `ready` ou `failed`.
- **FR-13** — Toda falha (limite excedido, PDF sem texto, quota estourada, rede indisponível) vira mensagem clara em pt-BR na UI, com ação de recuperação quando existir.

### Não-funcionais

- **NFR-1** — Um documento no teto configurado (50 páginas / 200.000 caracteres) conclui o processamento em ≤ 3 minutos no free tier, com progresso visível durante todo o período.
- **NFR-2** — A lógica de chunking vive em `backend/app/core/` e é testável sem rede e sem banco.
- **NFR-3** — Nenhuma chave de API aparece em log, em resposta de erro ou em mensagem de exceção.
- **NFR-4** — `make lint`, `make typecheck` e `make test` retornam zero.
- **NFR-5** — A partir de um clone limpo com `.env` preenchido, `docker compose up --build` sobe `db`, `backend` e `frontend`, e a tela de upload responde.
- **NFR-6** — Todos os limites e ids de modelo são configuráveis por variável de ambiente, sem recompilar imagem.
- **NFR-7** — O upload não bloqueia o event loop: leitura do arquivo e processamento acontecem fora do caminho da resposta HTTP.

## 3. Critérios de aceite

- **AC-1** (FR-1, NFR-7) — *Dado* um PDF válido de 3 páginas, *quando* faço `POST /api/documents`, *então* recebo `202` com `{id, status: "pending"}` em menos de 2 segundos, e o processamento continua em background.
- **AC-2** (FR-2) — *Dado* um arquivo de 30 MB com `MAX_UPLOAD_MB=25`, *quando* faço o upload, *então* recebo `413` e a mensagem em pt-BR cita o limite de tamanho.
- **AC-3** (FR-2) — *Dado* um PDF com 80 páginas e `MAX_PDF_PAGES=50`, *quando* faço o upload, *então* recebo `422` e a mensagem em pt-BR cita o limite de páginas.
- **AC-4** (FR-2) — *Dado* um arquivo `.txt` renomeado para `.pdf`, *quando* faço o upload, *então* recebo `422` informando que o arquivo não é um PDF válido.
- **AC-5** (FR-3) — *Dado* um PDF sem camada de texto, *quando* faço o upload, *então* o documento termina em `failed` com mensagem em pt-BR explicando que não há texto extraível e que OCR não é suportado.
- **AC-6** (FR-4, FR-5) — *Dado* um texto de duas páginas conhecidas, *quando* rodo extração e chunking, *então* cada chunk resultante carrega o número correto da página de origem e seu índice sequencial, e rodar duas vezes produz exatamente o mesmo resultado.
- **AC-7** (FR-5) — *Dado* um parágrafo que caberia inteiro dentro da janela, *quando* o chunking roda, *então* o corte não acontece no meio de uma palavra e chunks consecutivos compartilham `CHUNK_OVERLAP` caracteres.
- **AC-8** (FR-6) — *Dado* um documento que gera 250 chunks e `EMBEDDING_BATCH_SIZE=100`, *quando* o pipeline roda, *então* o adapter faz 3 requisições de embedding, não 250.
- **AC-9** (FR-6) — *Dado* que a primeira chamada de embedding retorna `429`, *quando* o adapter tenta de novo, *então* ele espera com backoff exponencial e conclui sem perder chunks.
- **AC-10** (FR-7) — *Dado* `GEMINI_API_KEYS` com duas chaves e a primeira retornando `429`, *quando* o adapter processa, *então* a requisição seguinte usa a segunda chave.
- **AC-11** (FR-8) — *Dado* um documento processado, *quando* consulto a tabela `chunks`, *então* cada linha tem `document_id`, `page_number`, `chunk_index`, `content` e `embedding` não nulo, e existe índice HNSW sobre `embedding`.
- **AC-12** (FR-9, FR-10) — *Dado* um upload em andamento, *quando* consulto `GET /api/documents/{id}` repetidamente, *então* observo a transição `pending → processing → ready`, com `chunks_processed` crescendo monotonicamente até `chunks_total`.
- **AC-13** (FR-9) — *Dado* que a API do Gemini falha de forma permanente, *quando* o processamento termina, *então* o documento fica em `failed` com mensagem em pt-BR, e nenhuma chave de API aparece na mensagem.
- **AC-14** (FR-11) — *Dado* que abro a tela de upload, *quando* arrasto um PDF válido, *então* vejo o nome do arquivo, o botão de envio habilitado e uma barra de progresso durante o envio.
- **AC-15** (FR-11) — *Dado* que seleciono um arquivo maior que o limite, *quando* tento enviar, *então* a UI bloqueia antes da requisição e explica o limite em pt-BR.
- **AC-16** (FR-12) — *Dado* um upload aceito, *quando* o processamento está em curso, *então* a UI mostra estado "processando" com progresso e faz a transição para "pronto" sem eu recarregar a página.
- **AC-17** (FR-13) — *Dado* que o backend responde `429`, *quando* a UI recebe o erro, *então* mostra mensagem em pt-BR explicando que o limite de uso foi atingido e oferece tentar de novo.
- **AC-18** (NFR-3) — *Dado* qualquer caminho de falha do adapter Gemini, *quando* inspeciono os logs e as respostas, *então* nenhuma chave de API aparece, nem parcialmente.
- **AC-19** (NFR-5) — *Dado* um clone limpo com `.env` preenchido, *quando* rodo `docker compose up --build`, *então* os três serviços sobem, `GET /api/health` responde `200` e a tela de upload carrega em `http://localhost:5173`.

## 4. Abordagem técnica

### Mapa NOVO vs. REUSADO vs. REMOVIDO

**REUSADO** (existe no repositório, será estendido ou consumido sem duplicar):

| Caminho | Como é reusado |
|---|---|
| `db/` | Recebe `001_init.sql`; já está montado em `docker-entrypoint-initdb.d` pelo `docker-compose.yml`. |
| `backend/app/core/` | Recebe os módulos puros de chunking. Pacote já existe. |
| `backend/app/adapters/` | Recebe extrator de PDF, cliente Gemini e repositório Postgres. Pacote já existe. |
| `backend/app/api/` | Recebe as rotas de documento. Pacote já existe. |
| `backend/tests/` | Recebe os testes. Pacote já existe. |
| `backend/pyproject.toml` | Alterado apenas se faltar dependência; `fastapi`, `asyncpg`, `pypdf`, `google-genai`, `pydantic-settings`, `python-multipart` já estão declarados. |
| `docker-compose.yml` | Alterado para acrescentar as novas variáveis de ambiente do backend. |
| `.env.example` | Alterado para documentar as novas variáveis. |
| `frontend/src/` | Recebe o app React. Pasta já existe (contém só `.gitkeep`). |
| `frontend/nginx.conf` | Consumido como está: `location /api/` já faz proxy para `backend:8000` com `proxy_buffering off`. |
| `frontend/vite.config.ts` | Consumido como está: proxy `/api` já configurado para dev fora do Docker. |
| `Makefile` | Consumido como está nesta spec; o alvo `eval` é acrescentado em `FEAT-0002`. |

**NOVO:**

- `db/001_init.sql` — extensão `vector`, tabelas `documents` e `chunks`, índice HNSW.
- `backend/app/config.py` — settings via `pydantic-settings`.
- `backend/app/main.py` — app FastAPI, ciclo de vida do pool, rota `/health`.
- `backend/app/core/chunking.py` — chunking puro e determinístico.
- `backend/app/core/models.py` — dataclasses de domínio (`PageText`, `Chunk`).
- `backend/app/adapters/pdf.py` — extração com `pypdf`, página a página.
- `backend/app/adapters/gemini.py` — cliente de embeddings: batch, backoff, pool de chaves.
- `backend/app/adapters/repository.py` — persistência com SQL parametrizado.
- `backend/app/api/documents.py` — rotas de upload e de estado.
- `backend/app/api/schemas.py` — modelos Pydantic de request/response.
- `backend/app/ingestion.py` — orquestração do pipeline em background.
- `backend/tests/*` — unitários de `core/` e integração de API com adapter falso.
- `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/index.css`, `frontend/src/App.tsx` — bootstrap do app.
- `frontend/src/lib/api.ts`, `frontend/src/lib/session.ts`, `frontend/src/lib/types.ts` — cliente HTTP, identidade de sessão, tipos.
- `frontend/src/components/*`, `frontend/src/hooks/*` — dropzone, progresso, estados.
- `frontend/eslint.config.js` — config do eslint 9 (flat config), exigida pelo script `npm run lint`.

**REMOVIDO:** nada. `frontend/src/.gitkeep` e `db/.gitkeep` deixam de ser necessários quando as pastas ganham conteúdo real.

### Modelo de dados

```sql
documents(id uuid pk, filename text, status text, error_message text,
          page_count int, chunks_total int, chunks_processed int,
          session_id text, created_at timestamptz)
chunks(id bigserial pk, document_id uuid fk, chunk_index int,
       page_number int, content text, embedding vector(N))
```

`session_id` entra já nesta spec, mesmo com uma sessão só em uso, porque `FEAT-0003` depende dele e acrescentá-lo depois custaria migração. `N` (dimensão do vetor) vem de `EMBEDDING_DIM`, configurável, porque depende do modelo de embedding escolhido.

### Restrições de free tier e como o desenho responde

| Restrição medida | Efeito | Resposta no desenho |
|---|---|---|
| Embeddings ~30.000 TPM | ~53k tokens (50 páginas) levam ~1,8 min | Processamento assíncrono + estado consultável (FR-9, FR-10) |
| Embeddings ~100 RPM | Uma requisição por chunk estouraria | Batch de até `EMBEDDING_BATCH_SIZE` por requisição (FR-6) |
| Embeddings ~1.000 RPD | Não é gargalo com batch | Nenhuma medida adicional |
| Limites são por projeto, não por chave | Duas chaves da mesma conta não somam | Pool opcional documentado como útil só entre contas distintas (FR-7) |
| Números não publicados oficialmente | Qualquer constante fixa envelhece | Tudo por env + backoff que não depende do valor exato (NFR-6, FR-6) |

### Configuração (todas com default seguro)

`DATABASE_URL`, `GEMINI_API_KEY`, `GEMINI_API_KEYS`, `GEMINI_EMBEDDING_MODEL`, `EMBEDDING_DIM`, `EMBEDDING_BATCH_SIZE`, `MAX_UPLOAD_MB`, `MAX_PDF_PAGES`, `MAX_EXTRACTED_CHARS`, `CHUNK_SIZE`, `CHUNK_OVERLAP`.

## 5. Plano de desenvolvimento por fases

> Cada fase é executável isoladamente por um agente lendo só este documento. Uma fase só inicia quando todas as fases listadas em "Depende de" estão concluídas. Os tracks A e B correm em paralelo; as dependências cruzadas estão declaradas por `id`.

### Track A — Backend

### Fase A.1 — Fundação: schema, config e app *(tamanho M)*

- **id:** `A.1`
- **slug:** `foundation`
- **Objetivo:** fazer `docker compose up --build` subir de verdade — banco com schema e extensão `vector`, app FastAPI respondendo `/health` com o banco conectado.
- **Depende de:** nenhuma
- **Arquivos novos:** `db/001_init.sql`, `backend/app/config.py`, `backend/app/main.py`, `backend/app/adapters/db.py`, `backend/tests/test_health.py`. **Arquivos alterados:** `docker-compose.yml`, `.env.example`, `backend/app/__init__.py`.
- **Passos:** 1) escrever `db/001_init.sql` com `CREATE EXTENSION IF NOT EXISTS vector`, tabelas `documents` e `chunks` conforme §4, e índice HNSW sobre `chunks.embedding`; 2) escrever `config.py` com `pydantic-settings` expondo todas as variáveis de §4 com defaults seguros; 3) escrever `adapters/db.py` com pool `asyncpg` criado no lifespan; 4) escrever `main.py` com o app, o lifespan e `GET /api/health` que faz `SELECT 1`; 5) acrescentar as novas variáveis a `docker-compose.yml` e `.env.example`; 6) subir o compose e confirmar os três serviços.
- **Testes:** `/health` responde `200` com banco conectado (AC-19); settings carregam defaults quando a env não está definida.
- **Escopo travado / violações BLOQUEANTES:** não usar ORM nem query builder; não concatenar SQL com input; não expor `DATABASE_URL` nem chave em resposta ou log; não criar rota de documento nesta fase.
- **Critério de conclusão (gate):** `docker compose up --build` sobe `db`, `backend` e `frontend`; `curl localhost:8000/api/health` responde `200`; `make lint typecheck test` zero.

### Fase A.2 — Extração de PDF e validação de entrada *(tamanho M)*

- **id:** `A.2`
- **slug:** `pdf-extraction`
- **Objetivo:** transformar bytes de PDF em texto por página, recusando com clareza tudo que viola os limites.
- **Depende de:** `A.1`
- **Arquivos novos:** `backend/app/adapters/pdf.py`, `backend/app/core/models.py`, `backend/tests/test_pdf_extraction.py`, `backend/tests/fixtures/` (PDFs mínimos gerados em código, não binários commitados). **Arquivos alterados:** nenhum.
- **Passos:** 1) definir `PageText(page_number, text)` e `Chunk(...)` em `core/models.py` como dataclasses puras; 2) implementar `extract_pages(data: bytes) -> list[PageText]` com `pypdf`, preservando o número de página base 1; 3) implementar as validações: assinatura `%PDF`, contagem de páginas contra `MAX_PDF_PAGES`, soma de caracteres extraídos contra `MAX_EXTRACTED_CHARS`; 4) levantar exceções de domínio distintas por tipo de violação, cada uma com mensagem em pt-BR; 5) tratar o caso de zero caractere extraível como erro próprio ("PDF sem texto extraível; OCR não é suportado").
- **Testes:** página e número corretos (AC-6); arquivo não-PDF recusado (AC-4); excesso de páginas recusado (AC-3); PDF sem texto recusado (AC-5).
- **Escopo travado / violações BLOQUEANTES:** não fazer OCR nem adicionar dependência de imagem; não engolir exceção do `pypdf` em `except` amplo sem reclassificar; não commitar PDF binário grande como fixture.
- **Critério de conclusão (gate):** testes da fase verdes; `make lint typecheck test` zero.

### Fase A.3 — Chunking determinístico *(tamanho S)*

- **id:** `A.3`
- **slug:** `chunking`
- **Objetivo:** quebrar o texto em chunks de tamanho útil, com página de origem preservada, de forma pura e determinística.
- **Depende de:** nenhuma
- **Arquivos novos:** `backend/app/core/chunking.py`, `backend/tests/test_chunking.py`. **Arquivos alterados:** `backend/app/core/models.py` (se `Chunk` ainda não existir, criar aqui).
- **Passos:** 1) implementar `chunk_pages(pages: list[PageText], size: int, overlap: int) -> list[Chunk]`; 2) preferir corte em fronteira de parágrafo (`\n\n`), depois de sentença, depois de espaço — nunca no meio de palavra; 3) aplicar `overlap` entre chunks consecutivos; 4) atribuir `chunk_index` sequencial no documento e `page_number` da página de origem do início do chunk; 5) normalizar espaços em branco excessivos sem destruir a fronteira de parágrafo.
- **Testes:** determinismo — duas execuções idênticas (AC-6); corte não parte palavra e overlap é respeitado (AC-7); página de origem correta em texto multi-página (AC-6); texto menor que a janela vira um chunk só.
- **Escopo travado / violações BLOQUEANTES:** este módulo não pode importar `fastapi`, `asyncpg`, `google.genai` nem tocar em I/O — violação do princípio 1; não usar biblioteca de splitter de terceiros (princípio 2).
- **Critério de conclusão (gate):** testes verdes rodando sem rede e sem banco; `make lint typecheck test` zero.

### Fase A.4 — Adapter Gemini de embeddings *(tamanho M)*

- **id:** `A.4`
- **slug:** `gemini-embeddings`
- **Objetivo:** converter listas de texto em vetores respeitando as restrições do free tier, sem vazar segredo.
- **Depende de:** `A.1`
- **Arquivos novos:** `backend/app/adapters/gemini.py`, `backend/tests/test_gemini_adapter.py`. **Arquivos alterados:** `.env.example`.
- **Passos:** 1) definir um protocolo `EmbeddingClient` com `embed_documents(texts) -> list[list[float]]` e `embed_query(text) -> list[float]`; 2) implementar o cliente Gemini usando `google-genai`, agrupando em lotes de `EMBEDDING_BATCH_SIZE`; 3) implementar retry com backoff exponencial e jitter para erro transitório e `429`, com teto de tentativas configurável; 4) implementar o pool: `GEMINI_API_KEYS` (lista) tem precedência sobre `GEMINI_API_KEY`, com round-robin e troca de chave em `429`; 5) garantir que nenhuma mensagem de erro propagada contenha a chave — sanitizar antes de relançar; 6) confirmar o id vigente do modelo de embedding e o valor de `EMBEDDING_DIM` na documentação do provedor, registrando-os em `.env.example`.
- **Testes:** batching reduz requisições (AC-8); `429` aciona backoff e conclui (AC-9); pool troca de chave em `429` (AC-10); chave nunca aparece na exceção propagada (AC-18). Todos com cliente HTTP falso — nenhum teste chama a API real.
- **Escopo travado / violações BLOQUEANTES:** não logar a chave nem fragmento dela; não fazer uma requisição por chunk; não usar `except Exception` sem reclassificar; não deixar retry infinito.
- **Critério de conclusão (gate):** testes verdes sem rede; `make lint typecheck test` zero.

### Fase A.5 — Pipeline de ingestão e rotas *(tamanho L)*

- **id:** `A.5`
- **slug:** `ingestion-pipeline`
- **Objetivo:** amarrar upload, extração, chunking, embeddings e persistência numa máquina de estados consultável.
- **Depende de:** `A.2`, `A.3`, `A.4`
- **Arquivos novos:** `backend/app/adapters/repository.py`, `backend/app/ingestion.py`, `backend/app/api/documents.py`, `backend/app/api/schemas.py`. **Arquivos alterados:** `backend/app/main.py` (registrar o router).
- **Passos:** 1) implementar o repositório com SQL parametrizado: criar documento, atualizar estado e progresso, inserir chunks em lote; 2) implementar `POST /api/documents` — validar, persistir o documento em `pending`, agendar `BackgroundTasks` e responder `202` com o id; 3) implementar o pipeline: `processing` → extrair → chunkar → embedar em lotes, atualizando `chunks_processed` a cada lote → `ready`; 4) capturar exceção de domínio e registrar `failed` com a mensagem em pt-BR correspondente; 5) implementar `GET /api/documents/{id}` devolvendo estado, progresso e erro; 6) ler o arquivo de forma a não bloquear o event loop; 7) associar `session_id` (header `X-Session-Id`) ao documento.
- **Testes:** upload responde rápido e em `pending` (AC-1); limites recusados com o status certo (AC-2, AC-3, AC-4); PDF sem texto termina `failed` (AC-5); transição de estado observável com progresso monotônico (AC-12); falha permanente vira `failed` sem vazar chave (AC-13); chunks persistidos com todos os campos (AC-11).
- **Escopo travado / violações BLOQUEANTES:** nenhuma chamada ao Gemini fora do adapter da `A.4`; nenhum SQL concatenado; não deixar o documento preso em `processing` quando há exceção — o `failed` é obrigatório em todo caminho de erro; não implementar retrieval nem chat aqui.
- **Critério de conclusão (gate):** upload real de um PDF de 3 páginas chega a `ready` com chunks embedados no banco; `make lint typecheck test` zero.

### Fase A.6 — Testes de integração da ingestão *(tamanho M)*

- **id:** `A.6`
- **slug:** `ingestion-tests`
- **Objetivo:** provar o fluxo ponta a ponta do backend com um adapter Gemini falso, de forma determinística e offline.
- **Depende de:** `A.5`
- **Arquivos novos:** `backend/tests/conftest.py`, `backend/tests/test_ingestion_api.py`, `backend/tests/fakes.py`. **Arquivos alterados:** `backend/pyproject.toml` (só se faltar dependência de teste).
- **Passos:** 1) criar `FakeEmbeddingClient` determinístico (vetor derivado de hash do texto) implementando o protocolo da `A.4`; 2) injetar o fake por override de dependência do FastAPI; 3) escrever o teste de fluxo `upload → polling → ready → chunks no banco`; 4) escrever os testes de recusa por limite e de falha de provedor; 5) garantir que a suíte não faz nenhuma chamada de rede.
- **Testes:** cobre AC-1, AC-2, AC-3, AC-4, AC-5, AC-11, AC-12, AC-13, AC-18.
- **Escopo travado / violações BLOQUEANTES:** nenhum teste pode chamar a API real do Gemini nem depender de chave; nenhum `skip` ou `retry` para mascarar flakiness; não testar implementação privada quando a rota cobre o comportamento.
- **Critério de conclusão (gate):** `make test` verde sem `GEMINI_API_KEY` definida; `make lint typecheck` zero.

### Track B — Frontend

### Fase B.1 — Bootstrap do app *(tamanho M)*

- **id:** `B.1`
- **slug:** `app-shell`
- **Objetivo:** ter o React rodando dentro do container, com Tailwind, cliente HTTP e identidade de sessão.
- **Depende de:** nenhuma
- **Arquivos novos:** `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`, `frontend/src/lib/api.ts`, `frontend/src/lib/session.ts`, `frontend/src/lib/types.ts`, `frontend/eslint.config.js`. **Arquivos alterados:** nenhum — `frontend/vite.config.ts`, `frontend/tsconfig.json` e `frontend/nginx.conf` já servem como estão.
- **Passos:** 1) criar `index.html` e `main.tsx` montando o `App`; 2) importar Tailwind 4 via `@import "tailwindcss"` em `index.css`; 3) implementar `session.ts` — lê UUID de `localStorage`, gera com `crypto.randomUUID()` na primeira visita; 4) implementar `api.ts` — wrapper de `fetch` com base `/api`, header `X-Session-Id` e normalização de erro para um tipo próprio; 5) declarar em `types.ts` os tipos espelhando os schemas da `A.5`; 6) criar `eslint.config.js` (flat config) para o script `npm run lint` funcionar.
- **Testes:** `npx tsc --noEmit` zero; `npm run lint` zero; build do container serve a página em `localhost:5173`.
- **Escopo travado / violações BLOQUEANTES:** não instalar biblioteca de estado nem de UI kit — React e Tailwind bastam; não hardcodar URL absoluta de backend (o proxy resolve); não afrouxar `strict` do TypeScript.
- **Critério de conclusão (gate):** `docker compose up --build` serve a página; `npm run lint` e `tsc --noEmit` zero.

### Fase B.2 — Tela de upload *(tamanho M)*

- **id:** `B.2`
- **slug:** `upload-view`
- **Objetivo:** permitir enviar um PDF com validação local e progresso de envio.
- **Depende de:** `B.1`, `A.5`
- **Arquivos novos:** `frontend/src/components/UploadDropzone.tsx`, `frontend/src/hooks/useUpload.ts`. **Arquivos alterados:** `frontend/src/App.tsx`.
- **Passos:** 1) implementar dropzone com clique e arrastar-soltar, aceitando só `application/pdf`; 2) validar extensão e tamanho no cliente contra os mesmos limites do servidor, expostos por env de build ou constantes documentadas; 3) implementar `useUpload` enviando `FormData` e acompanhando progresso; 4) exibir nome, tamanho e botão de envio; 5) ao receber `202`, guardar o id do documento e passar o controle para o acompanhamento de estado.
- **Testes:** envio de PDF válido mostra progresso e transita para acompanhamento (AC-14); arquivo acima do limite é bloqueado antes da requisição, com mensagem em pt-BR (AC-15).
- **Escopo travado / violações BLOQUEANTES:** validação no cliente é conveniência e **não** substitui a do servidor (princípio 4); não aceitar outros formatos; textos da UI em pt-BR e identificadores em inglês (princípio 6).
- **Critério de conclusão (gate):** upload real de ponta a ponta contra o backend rodando; `npm run lint` e `tsc --noEmit` zero.

### Fase B.3 — Acompanhamento do processamento *(tamanho M)*

- **id:** `B.3`
- **slug:** `processing-status`
- **Objetivo:** mostrar honestamente o que está acontecendo enquanto o documento é processado.
- **Depende de:** `B.2`
- **Arquivos novos:** `frontend/src/components/ProcessingStatus.tsx`, `frontend/src/hooks/useDocumentStatus.ts`. **Arquivos alterados:** `frontend/src/App.tsx`.
- **Passos:** 1) implementar `useDocumentStatus` com polling de `GET /api/documents/{id}` em intervalo configurável, parando em `ready` ou `failed`; 2) renderizar os quatro estados com rótulo em pt-BR e barra de progresso derivada de `chunks_processed / chunks_total`; 3) tratar `chunks_total` ainda desconhecido com indicador indeterminado; 4) limpar o timer ao desmontar; 5) ao chegar em `ready`, sinalizar que o documento está pronto para conversa.
- **Testes:** transição visível sem recarregar a página (AC-16); progresso monotônico refletido na barra (AC-12).
- **Escopo travado / violações BLOQUEANTES:** não fazer polling agressivo (intervalo mínimo de 1s); não deixar timer órfão após desmontar; não inventar progresso falso quando o backend não informa.
- **Critério de conclusão (gate):** fluxo `upload → processando → pronto` observável na UI; `npm run lint` e `tsc --noEmit` zero.

### Fase B.4 — Estados de erro e acabamento *(tamanho S)*

- **id:** `B.4`
- **slug:** `error-states`
- **Objetivo:** transformar toda falha possível em mensagem acionável em pt-BR.
- **Depende de:** `B.3`
- **Arquivos novos:** `frontend/src/components/ErrorBanner.tsx`, `frontend/src/lib/errors.ts`. **Arquivos alterados:** `frontend/src/components/UploadDropzone.tsx`, `frontend/src/components/ProcessingStatus.tsx`, `frontend/src/App.tsx`.
- **Passos:** 1) mapear em `errors.ts` cada condição — `413`, `422`, `429`, `5xx`, rede indisponível, documento `failed` — para uma mensagem em pt-BR e uma ação sugerida; 2) renderizar o banner de erro com a ação (tentar de novo, escolher outro arquivo); 3) cobrir o estado vazio inicial com uma instrução clara; 4) garantir foco e rótulos acessíveis nos controles interativos.
- **Testes:** `429` vira mensagem de limite de uso com ação de repetir (AC-17); documento `failed` mostra a mensagem vinda do backend (AC-5).
- **Escopo travado / violações BLOQUEANTES:** nunca exibir stack trace, corpo bruto de erro ou nome de exceção ao usuário; nunca exibir chave de API; não usar `alert()`.
- **Critério de conclusão (gate):** cada erro da tabela de `errors.ts` reproduzido manualmente exibe a mensagem correta; `npm run lint` e `tsc --noEmit` zero.

## 6. Riscos

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| 1 | Id do modelo de embedding ou `EMBEDDING_DIM` diferente do assumido, quebrando a coluna `vector(N)` | Média | Alto | Confirmar o id e a dimensão na `A.4` **antes** de rodar `A.5`; `EMBEDDING_DIM` é env e `001_init.sql` usa o valor decidido na `A.1` |
| 2 | Quota do free tier estourar durante a avaliação | Média | Alto | Limites conservadores por env, batch, backoff e pool opcional de chaves; mensagem clara em pt-BR no `429` |
| 3 | `init.sql` não reaplicar após mudança de schema (só roda em banco vazio) | Alta | Médio | Documentado na constitution e no README: `make down` remove o volume antes do próximo `up` |
| 4 | `BackgroundTasks` perder o processamento se o container reiniciar | Baixa | Médio | Documento fica em `processing`; a UI mostra o estado e o usuário reenvia. Fila durável está fora de escopo |
| 5 | PDF com layout complexo produzir texto embaralhado | Média | Médio | `pypdf` extrai por página; qualidade validada com o PDF de exemplo da YAITEC na `A.2` |
| 6 | Tracks A e B divergirem no contrato da API | Média | Médio | `frontend/src/lib/types.ts` espelha `backend/app/api/schemas.py`; `B.2` depende explicitamente de `A.5` |

## 7. Rollout

Não há produção nem feature flag: a entrega é o repositório privado com `docker compose up`. A ordem de rollout é a ordem das fases — `A.1` primeiro, porque é ela que faz o compose subir de verdade e destrava todo o resto.

Os dois tracks correm em paralelo até `B.2`, que é o primeiro ponto de acoplamento (depende de `A.5`). `B.1` pode ser feita a qualquer momento, inclusive antes de `A.1`.

Rollback é `git revert` da fase: cada fase é um incremento testável e independente. Mudança de schema exige `make down` (remove o volume) antes do próximo `up`.

## 8. Open Questions

- **OQ-1 — Estratégia de chunking.** **RESOLVIDO (2026-08-17):** janela de ~1000 caracteres com 150 de overlap, cortando em fronteira de parágrafo/sentença, carregando o número da página. *Justificativa:* dá granularidade útil para citação por página sem fragmentar frase; overlap evita perder contexto na fronteira. *Rejeitado:* chunk por token (o tokenizador do Gemini não é exposto localmente, o que tornaria o chunking não-determinístico offline) e chunk por página inteira (grosso demais — a citação perderia precisão).
- **OQ-5 — Processamento síncrono ou assíncrono.** **RESOLVIDO (2026-08-17):** `BackgroundTasks` com máquina de estados consultada por polling. *Justificativa:* com ~30k TPM de embeddings, 50 páginas levam ~1,8 min — muito além de qualquer timeout de request; e o desafio pede explicitamente "mostre ao usuário que está processando". *Rejeitado:* processamento síncrono na request.
- **OQ-7 — Limites do PDF aceito.** **RESOLVIDO (2026-08-17):** `MAX_UPLOAD_MB=25` protegendo upload e disco; `MAX_PDF_PAGES=50` e `MAX_EXTRACTED_CHARS=200000` protegendo a quota de embeddings. *Justificativa:* megabytes são proxy ruim de custo de embedding — um PDF de imagens pesa muito e custa pouco, texto denso pesa pouco e custa caro. Separar os limites por aquilo que cada um protege é mais preciso e mais fácil de explicar. *Rejeitado:* limite único em MB.
- **OQ-8 — Pool de chaves Gemini.** **RESOLVIDO (2026-08-17):** suportado e opcional via `GEMINI_API_KEYS`, com round-robin e failover em `429`. *Justificativa:* custa ~20 linhas no adapter, funciona idêntico com uma chave só, e dá saída se a quota apertar. *Ressalva registrada:* limites do free tier são por projeto, não por chave — só dobra de verdade com chaves de contas Google distintas.
- **OQ-9 — Dimensão do vetor (`EMBEDDING_DIM`).** **ABERTA.** Depende do id de modelo de embedding vigente, a confirmar na `A.4` contra a documentação do provedor. Enquanto não confirmada, `001_init.sql` usa o valor de `EMBEDDING_DIM` decidido na `A.1` e a `A.4` valida a coerência antes de `A.5` rodar. Resolver **antes** de processar qualquer documento real evita recriar o volume.

## 9. Definition of Done (gate por etapa)

**Gate por fase** — cada uma só fecha com seu critério de conclusão verde:

- [ ] `A.1 foundation` — compose sobe os três serviços; `/api/health` responde `200`.
- [ ] `A.2 pdf-extraction` — extração por página correta; todas as recusas com mensagem em pt-BR.
- [ ] `A.3 chunking` — chunking determinístico, testado sem rede e sem banco.
- [ ] `A.4 gemini-embeddings` — batch, backoff e pool testados com cliente falso; chave nunca vaza.
- [ ] `A.5 ingestion-pipeline` — PDF real chega a `ready` com chunks embedados.
- [ ] `A.6 ingestion-tests` — suíte de integração verde sem `GEMINI_API_KEY` definida.
- [ ] `B.1 app-shell` — página servida pelo container; lint e typecheck zero.
- [ ] `B.2 upload-view` — upload de ponta a ponta contra o backend.
- [ ] `B.3 processing-status` — transição de estado visível sem recarregar.
- [ ] `B.4 error-states` — cada erro mapeado exibe mensagem acionável em pt-BR.

**Itens globais transversais:**

- [ ] Cada FR desta spec tem ao menos um AC verificado.
- [ ] `make lint`, `make typecheck` e `make test` retornam zero.
- [ ] Nenhum módulo de `backend/app/core/` importa `fastapi`, `asyncpg` ou `google.genai` (princípio 1).
- [ ] Nenhuma dependência de framework de RAG foi adicionada (princípio 2).
- [ ] Nenhuma chave de API, `DATABASE_URL` ou PII aparece em log, resposta de erro ou arquivo versionado (princípio 3).
- [ ] Todo SQL é parametrizado (princípio 5).
- [ ] Identificadores em inglês; textos de UI e mensagens de erro em pt-BR (princípio 6).
- [ ] A suíte de testes roda offline, sem chave de API e sem chamada de rede (princípio 7).
- [ ] `docker compose up --build` a partir de clone limpo sobe tudo e a tela de upload responde (princípio 9).
- [ ] `.env.example` documenta toda variável nova introduzida.
- [ ] Nenhuma regressão nas fases anteriores desta spec.
