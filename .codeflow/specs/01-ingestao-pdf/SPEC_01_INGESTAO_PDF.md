---
id: FEAT-0001
slug: 01-ingestao-pdf
title: "Ingestão de PDF: upload, extração por página, chunking, embeddings e vector store"
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
blocks: [FEAT-0002]
quality_gate:
  scorer: phase-evaluator
  threshold: 8.5
---

# FEAT-0001 — Ingestão de PDF

> **Nota de planning (2026-08-17, revisada):** esta spec foi reescrita após revisão adversarial por cinco revisores independentes. Os defeitos de infraestrutura que eles encontraram **já foram corrigidos no esqueleto** e são pré-condição desta spec, não trabalho dela — ver §4 "Estado corrigido do esqueleto". As decisões de contrato (modelo de embedding, dimensão, chunking por página) estão fixadas aqui, não em Open Question: os scripts de `db/` só rodam em banco vazio, então errar custa `make down` e reingestão. Registro completo em `.codeflow/decisions/2026-08-17-revisao-adversarial-das-specs.md`.
>
> **Fora do escopo desta spec:** chat, retrieval e geração (`FEAT-0002`); biblioteca de múltiplos documentos (cortada — ver a decision); autenticação e autorização por sessão; formatos além de PDF; OCR; deploy e CI; testes E2E de browser; observabilidade.

## Resumo executivo (TL;DR)

| | |
|---|---|
| **O quê** | Uma pessoa envia um PDF; o sistema extrai o texto página a página, quebra em chunks que não cruzam fronteira de página, gera embeddings via Gemini e persiste no pgvector, com o estado do processamento visível. |
| **Por quê** | É o requisito 1 do desafio e a fundação de tudo: sem chunks embedados e citáveis por página, não existe RAG fundamentado nem citação verificável. |
| **Backend-Infra** | Schema com `vector(768)` e índice HNSW de cosseno; config por env; envelope de erro único; upload assíncrono com máquina de estados; adapter Gemini com lote, backoff, `task_type` e normalização L2. |
| **Frontend** | Tela de upload com dropzone, limites lidos da API, acompanhamento do processamento e mensagens de erro em pt-BR mapeadas por código. |
| **Decisão** | Chunking por página (citação exata por construção); dimensão 768 fixa no schema (o HNSW não indexa acima de 2000); tudo que exige parse do PDF acontece em background. |
| **Tamanho** | M — 5 fases no Track A (backend) e 3 no Track B (frontend). |

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

O desafio da YAITEC pede um app onde a pessoa envia um PDF e conversa com ele, com respostas fundamentadas citando trecho ou página. Antes de qualquer conversa, o documento precisa virar dado consultável por similaridade: texto extraído, quebrado em pedaços de tamanho útil, convertido em vetores e guardado num índice.

**O detalhe que decide a nota está na extração.** Se o PDF for extraído como um texto único e só depois cortado, o número da página se perde e citar vira adivinhação. Extrair por página e nunca deixar um chunk cruzar a fronteira faz a citação ser exata por construção — e o avaliador confere contra um PDF de 3 páginas que ele mesmo enviou.

**As quotas do free tier ditaram a arquitetura, não o estilo.** O gargalo medido é o TPM de embeddings (~30.000 tokens/min); o número de requisições não é problema porque o lote resolve. Um documento no teto desta spec (20 páginas, 60.000 caracteres, ~16k tokens) leva por volta de 40 segundos só embedando. Nenhum request HTTP sobrevive a isso — daí o processamento assíncrono e o estado visível. O requisito "mostre ao usuário que está processando" é consequência da quota.

O repositório já tem o esqueleto do `/bootstrap` com os seams prontos e **os seis defeitos de infraestrutura corrigidos** (§4).

### 1.1 Princípios invioláveis

Cada um rastreia a uma regra existente. Os itens 1–5 vêm de `.codeflow/constitution.md`, que está neste repositório; os itens 6–9 vêm das rules universais do framework codeflow do autor (`~/.codeflow/framework/core/rules/`), que não são versionadas aqui.

1. **`backend/app/core/` não importa `fastapi`, `asyncpg` nem `google.genai`.** — `constitution.md`, `## Regras invariantes específicas`. É o que torna o chunking testável sem rede e sem banco.
2. **Frameworks de RAG são proibidos** (`langchain`, `llama-index` e equivalentes fora das dependências). — idem.
3. **Segredos só em variável de ambiente, nunca em log ou mensagem de exceção.** — idem, e rule `security`.
4. **`mypy --strict` e `tsc` strict retornam zero; nenhum gate é afrouxado para fazer código passar.** — idem.
5. **De um clone limpo, `docker compose up --build` sobe a aplicação inteira.** — idem, `## Áreas de alto risco`.
6. **Toda entrada externa é validada no servidor; validação no cliente é conveniência.** — rule `security`.
7. **SQL parametrizado; nunca concatenação com input externo.** — rule `security`.
8. **Identificadores em inglês; textos ao usuário em pt-BR.** — rule `naming`.
9. **Todo código novo tem teste; teste descreve comportamento e é determinístico.** — rule `testing`.

## 2. Requisitos

### Funcionais

- **FR-1** — `POST /api/documents` aceita upload multipart (campo `file`) de um PDF e responde `202` com `{id, status}` sem aguardar o processamento.
- **FR-2** — Na requisição, antes de ler o corpo inteiro, o servidor rejeita: `Content-Length` acima de `MAX_UPLOAD_MB` (`413`) e arquivo cuja assinatura não comece por `%PDF` (`422`). A leitura do corpo é cortada rigidamente no limite.
- **FR-3** — Tudo que exige parse do PDF — contagem de páginas contra `MAX_PDF_PAGES`, total de caracteres contra `MAX_EXTRACTED_CHARS`, ausência de texto extraível — é validado **no processamento em background** e resulta em `failed` com mensagem em pt-BR específica de cada violação.
- **FR-4** — A extração produz o texto de cada página associado ao seu número (base 1), e roda fora do event loop.
- **FR-5** — O chunking é determinístico e **por página**: nenhum chunk cruza fronteira de página. Dentro da página, janela de `CHUNK_SIZE` com `CHUNK_OVERLAP`, cortando em fronteira de parágrafo, depois de sentença, depois de espaço — nunca no meio de palavra. Cada chunk carrega `page_number` e `chunk_index` sequencial no documento.
- **FR-6** — Os embeddings são gerados em lote de até `EMBEDDING_BATCH_SIZE` textos, com `task_type=RETRIEVAL_DOCUMENT`, `output_dimensionality=EMBEDDING_DIM` e normalização L2 do vetor retornado. Erro transitório e `429` acionam backoff exponencial com jitter e teto de tentativas; erro de payload grande (`400`) é permanente e não é repetido.
- **FR-7** — O adapter expõe também `embed_query`, com `task_type=RETRIEVAL_QUERY` e a mesma normalização — implementado e testado nesta spec, consumido pela `FEAT-0002`.
- **FR-8** — Documento e chunks são persistidos no Postgres; o vetor vive em `vector(768)` com índice `USING hnsw (embedding vector_cosine_ops)`.
- **FR-9** — O documento percorre `pending → processing → ready → failed`. Toda saída de erro grava `failed` com mensagem em pt-BR; nenhum caminho deixa o documento preso em `processing`.
- **FR-10** — `GET /api/documents/{id}` devolve estado, `chunks_processed`, `chunks_total`, `page_count` e `error_message`.
- **FR-11** — `GET /api/config` devolve os limites vigentes (`max_upload_mb`, `max_pdf_pages`, `max_extracted_chars`), para o cliente validar contra os mesmos números do servidor sem duplicá-los.
- **FR-12** — Upload do mesmo conteúdo (mesmo SHA-256) na mesma sessão devolve o documento existente em vez de reprocessar.
- **FR-13** — No startup, documentos presos em `pending` ou `processing` (restos de um restart) são marcados `failed` com mensagem orientando reenviar.
- **FR-14** — Todo erro da API usa o envelope `{"code": "<slug>", "message": "<pt-BR>"}`, incluindo os erros de validação do framework, via handler global.
- **FR-15** — A tela de upload permite selecionar ou arrastar um PDF, valida extensão e tamanho contra os limites de `GET /api/config` e mostra indicador de envio.
- **FR-16** — Após o envio, a UI acompanha `GET /api/documents/{id}` e exibe o estado com progresso derivado de `chunks_processed / chunks_total`, até `ready` ou `failed`, sem recarregar a página.
- **FR-17** — Toda falha vira mensagem em pt-BR na UI, mapeada pelo `code` do envelope, com ação de recuperação quando existir.

### Não-funcionais

- **NFR-1** — O estado de progresso é atualizado a cada lote de embeddings, no máximo a cada 15 segundos.
- **NFR-2** — A lógica de chunking vive em `backend/app/core/` e é testável sem rede e sem banco.
- **NFR-3** — Nenhuma chave de API aparece em log, resposta ou mensagem de exceção.
- **NFR-4** — `make lint`, `make typecheck` e `make test` retornam zero, e `make test` roda **sem `GEMINI_API_KEY` e sem banco**.
- **NFR-5** — De um clone limpo com `.env` preenchido, `docker compose up --build` sobe `db`, `backend` e `frontend`, e a tela de upload responde em `http://localhost:5173`.
- **NFR-6** — Limites, ids de modelo e parâmetros de chunking são configuráveis por env. **A dimensão do vetor é exceção declarada:** vive fixa no DDL, porque um `.sql` do `docker-entrypoint-initdb.d` não interpola variável; o lifespan valida a coerência entre coluna e configuração.
- **NFR-7** — O upload não bloqueia o event loop: leitura do arquivo e parse do PDF acontecem fora do caminho da resposta.
- **NFR-8** — Uma ingestão por vez (semáforo global): duas pipelines simultâneas disputariam o mesmo TPM e ambas cairiam em `429`.

## 3. Critérios de aceite

- **AC-1** (FR-1, NFR-7) — *Dado* um PDF válido de 3 páginas, *quando* faço `POST /api/documents`, *então* recebo `202` com `{id, status:"pending"}` em menos de 2 segundos e o processamento segue em background.
- **AC-2** (FR-2) — *Dado* um arquivo de 30 MB com `MAX_UPLOAD_MB=25`, *quando* faço o upload **através do nginx**, *então* recebo `413` com corpo JSON no envelope `{code, message}` em pt-BR — não HTML do nginx.
- **AC-3** (FR-2) — *Dado* um `.txt` renomeado para `.pdf`, *quando* faço o upload, *então* recebo `422` com `code: "arquivo_invalido"`.
- **AC-4** (FR-3) — *Dado* um PDF com 40 páginas e `MAX_PDF_PAGES=20`, *quando* o processamento roda, *então* o documento termina em `failed` com mensagem citando o limite de páginas.
- **AC-5** (FR-3) — *Dado* um PDF sem camada de texto, *quando* o processamento roda, *então* termina em `failed` explicando que não há texto extraível e que OCR não é suportado.
- **AC-6** (FR-4, FR-5) — *Dado* um texto de duas páginas conhecidas, *quando* rodo extração e chunking, *então* cada chunk carrega o número correto da página, **nenhum chunk contém texto de duas páginas**, e duas execuções produzem resultado idêntico.
- **AC-7** (FR-5) — *Dado* uma página maior que a janela, *quando* o chunking roda, *então* nenhum chunk começa ou termina no meio de uma palavra, e chunks consecutivos da mesma página compartilham ao menos `CHUNK_OVERLAP // 2` caracteres.
- **AC-8** (FR-6) — *Dado* N chunks e `EMBEDDING_BATCH_SIZE=B`, *quando* o pipeline roda, *então* o adapter faz exatamente `ceil(N/B)` requisições de embedding.
- **AC-9** (FR-6) — *Dado* que a primeira chamada retorna `429`, *quando* o adapter repete, *então* espera com backoff exponencial e conclui sem perder chunks; *dado* um `400` de payload grande, *então* não repete e falha com mensagem própria.
- **AC-10** (FR-6, FR-7) — *Dado* um vetor retornado pela API, *quando* o adapter o entrega, *então* sua norma L2 é 1,0 (tolerância 1e-6), e `embed_documents` e `embed_query` usam `task_type` diferentes.
- **AC-11** (FR-8) — *Dado* um documento processado, *quando* consulto `chunks`, *então* cada linha tem `document_id`, `page_number`, `chunk_index`, `content` e `embedding` não nulo, e `\d chunks` mostra índice HNSW com `vector_cosine_ops`.
- **AC-12** (FR-9, FR-10, NFR-1) — *Dado* um upload em andamento, *quando* consulto o estado repetidamente, *então* observo `pending → processing → ready` com `chunks_processed` crescendo monotonicamente até `chunks_total`.
- **AC-13** (FR-9, NFR-3) — *Dado* que a API do Gemini falha de forma permanente, *quando* o processamento termina, *então* o documento fica `failed` com mensagem em pt-BR e nenhuma chave aparece nela.
- **AC-14** (FR-11) — *Dado* que chamo `GET /api/config`, *então* recebo os três limites com os mesmos valores que o servidor aplica.
- **AC-15** (FR-12) — *Dado* que envio o mesmo PDF duas vezes na mesma sessão, *então* o segundo envio devolve o documento existente e **nenhum embedding novo é gerado**.
- **AC-16** (FR-13) — *Dado* um documento em `processing` e um restart do backend, *quando* o app sobe, *então* ele passa a `failed` com mensagem orientando reenviar.
- **AC-17** (FR-14) — *Dado* qualquer erro `4xx` ou `5xx` da API, *quando* inspeciono o corpo, *então* ele tem exatamente `{code, message}` — inclusive nos erros de validação do framework.
- **AC-18** (FR-15) — *Dado* que abro a tela, *quando* arrasto um PDF válido, *então* vejo nome, tamanho e indicador de envio; *quando* escolho um arquivo acima do limite lido de `GET /api/config`, *então* a UI bloqueia antes da requisição e explica o limite em pt-BR.
- **AC-19** (FR-16) — *Dado* um upload aceito, *quando* o processamento corre, *então* a UI mostra "processando" com progresso e transita para "pronto" sem recarregar.
- **AC-20** (FR-17) — *Dado* um erro com `code: "limite_de_uso"`, *quando* a UI o recebe, *então* mostra mensagem sobre limite de uso e oferece tentar de novo — sem exibir stack trace nem corpo bruto.
- **AC-21** (NFR-5) — *Dado* um clone limpo com `.env` preenchido, *quando* rodo `docker compose up --build`, *então* os três serviços sobem e **`curl http://localhost:5173/api/health` responde `200` através do nginx** (não só na porta 8000 direta).
- **AC-22** (NFR-6) — *Dado* que `EMBEDDING_DIM` no `.env` diverge da dimensão da coluna, *quando* o backend sobe, *então* ele falha rápido com mensagem clara em vez de aceitar `INSERT` que quebraria depois.

## 4. Abordagem técnica

### Estado corrigido do esqueleto (pré-condição, já aplicado)

Estes seis defeitos foram encontrados na revisão e **já estão corrigidos no repositório**. Nenhuma fase precisa refazê-los; qualquer um deles voltando é regressão bloqueante.

| Arquivo | O que estava errado | Correção aplicada |
|---|---|---|
| `frontend/nginx.conf` | `proxy_pass` com barra final removia o prefixo `/api` — o backend recebia `/documents` | barra removida; o prefixo é preservado |
| `frontend/nginx.conf` | sem `client_max_body_size`, o default de 1 MB recusava o upload com HTML antes de a API ver | `client_max_body_size 30m` |
| `docker-compose.yml` | `pg_isready` sem `-h` fica verde falando pelo socket unix, enquanto o TCP está fechado e o init ainda roda — o backend subia cedo e morria | `pg_isready -h 127.0.0.1`, com `start_period` |
| `docker-compose.yml` | sem `env_file`, só duas variáveis chegavam ao container; todo o resto usava default em silêncio | `env_file: .env`; `db` publica `5432` para testes e eval |
| `backend/Dockerfile` | `uv run` no CMD ressincronizava o grupo `dev` a cada start; sem lockfile, a resolução mudava a cada build | binário do venv direto; `uv sync --frozen`; `uv.lock` e `package-lock.json` commitados; `tests/` e `eval/` copiados |
| `backend/pyproject.toml` | `fastapi>=0.115` não tem SSE nativo | `fastapi>=0.135` (resolvido: 0.141.1, verificado) |

### Contrato de embedding (fixado, não é Open Question)

| Item | Valor | Por quê |
|---|---|---|
| Modelo | `gemini-embedding-001` | text-only basta; é o que expõe `task_type` |
| Dimensão | **768** via `output_dimensionality` | o default é 3072 e o índice HNSW do pgvector aceita no máximo 2000 — `CREATE INDEX` abortaria dentro do initdb |
| Normalização | **L2 manual, obrigatória** | o modelo só entrega vetor normalizado em 3072; sem normalizar, o cosseno mente |
| `task_type` | `RETRIEVAL_DOCUMENT` nos chunks, `RETRIEVAL_QUERY` na pergunta | é o mecanismo documentado pelo provedor para retrieval; custa um parâmetro |
| Índice | `USING hnsw (embedding vector_cosine_ops)` | sem opclass o `CREATE INDEX` nem compila, e um índice L2 não atende ao `<=>` de cosseno da `FEAT-0002` |
| Lote | `EMBEDDING_BATCH_SIZE=16` | 100 chunks passariam do teto de tokens por requisição e consumiriam quase todo o TPM de uma vez |

**Pré-condição verificada contra a API real, antes da fase `A.3`:** um script de ~10 linhas que embeda `["gato", "cachorro", "mecânica quântica"]` e afirma `len(embeddings) == 3` e `cos(v0,v1) > cos(v0,v2)`. O motivo é específico: o comportamento de lote difere entre modelos de embedding do provedor — há modelo que devolve **um único vetor agregado** quando vários textos vão direto na lista. Nenhum teste offline detecta isso, porque o fake devolve N vetores para N textos; o sintoma seria retrieval retornando chunks aleatórios com a suíte verde.

### Envelope de erro (fonte única, consumida pelos dois tracks)

Todo erro da API, incluindo os de validação do framework, sai como:

```json
{ "code": "arquivo_grande", "message": "O arquivo excede o limite de 25 MB." }
```

| `code` | Status | Quando |
|---|---|---|
| `arquivo_grande` | 413 | `Content-Length` acima de `MAX_UPLOAD_MB` |
| `arquivo_invalido` | 422 | assinatura não é `%PDF` |
| `nao_encontrado` | 404 | documento inexistente |
| `limite_de_uso` | 429 | quota do provedor |
| `erro_interno` | 500 | qualquer outra |

O frontend mapeia **por `code`**, nunca por status — é o que impede os dois tracks de divergirem e o que faz a mesma tabela valer na `FEAT-0002`.

### Contrato de API

```
POST /api/documents        multipart: file  → 202 {"id": "<uuid>", "status": "pending"}
GET  /api/documents/{id}         → 200 {"id","filename","status","page_count",
                                        "chunks_total","chunks_processed","error_message"}
GET  /api/config                 → 200 {"max_upload_mb","max_pdf_pages","max_extracted_chars"}
GET  /api/health                 → 200 {"status":"ok","database":"ok"}
```

`status` ∈ `pending | processing | ready | failed`. `X-Session-Id` é enviado pelo cliente e gravado no documento; **não é usado para autorização** nesta entrega — decisão registrada, e o README a declara como organização por browser, não fronteira de segurança.

### Modelo de dados

```sql
documents(id uuid pk default gen_random_uuid(), filename text, content_hash text,
          status text, error_message text, page_count int,
          chunks_total int, chunks_processed int,
          session_id text, created_at timestamptz default now(),
          unique (session_id, content_hash))
chunks(id bigserial pk,
       document_id uuid references documents(id) on delete cascade,
       chunk_index int, page_number int, content text, embedding vector(768))
```

`gen_random_uuid()` vem do `pgcrypto`, presente no PG16. O `ON DELETE CASCADE` é declarado **aqui**, por quem cria a tabela.

### Mapa NOVO vs. REUSADO vs. REMOVIDO

**REUSADO** (existe no repositório, verificado): `db/` montado em `docker-entrypoint-initdb.d`; `backend/app/{core,adapters,api}/` e `backend/tests/`; `backend/pyproject.toml` (já declara `fastapi`, `asyncpg`, `pypdf`, `google-genai`, `pydantic-settings`, `python-multipart`); `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/package.json`, `Makefile`, `.env.example` — todos já corrigidos; `frontend/src/`.

**NOVO:** `db/001_init.sql`; `backend/app/{config,main,errors,ingestion}.py`; `backend/app/core/{models,chunking}.py`; `backend/app/adapters/{db,pdf,gemini,repository}.py`; `backend/app/api/{documents,schemas}.py`; `backend/tests/{conftest,fakes,test_*}.py`; `backend/scripts/check_embeddings.py`; `frontend/index.html`; `frontend/src/{main.tsx,App.tsx,index.css}`; `frontend/src/lib/{api,session,types,errors,config}.ts`; `frontend/src/components/*`; `frontend/src/hooks/*`; `frontend/eslint.config.js`.

**REMOVIDO:** `db/.gitkeep` e `frontend/src/.gitkeep`, quando as pastas ganharem conteúdo.

### Restrições de free tier e como o desenho responde

| Restrição medida | Efeito | Resposta |
|---|---|---|
| Embeddings ~30k TPM | 20 páginas ≈ 16k tokens ≈ ~40 s | processamento assíncrono + estado consultável (FR-9, FR-10) |
| Teto de tokens por requisição | lote de 100 estouraria | `EMBEDDING_BATCH_SIZE=16` (FR-6) |
| Duas ingestões simultâneas | ambas caem em `429` | semáforo global (NFR-8) |
| Reenvio do mesmo PDF | queima quota à toa | dedup por `content_hash` (FR-12) |
| Números não publicados oficialmente | constante fixa envelhece | tudo por env + backoff que não depende do valor exato |

## 5. Plano de desenvolvimento por fases

> Cada fase é executável isoladamente por um agente lendo só este documento. Uma fase só inicia quando todas as listadas em "Depende de" estão concluídas. Os tracks A e B correm em paralelo; o acoplamento está declarado por `id`.

### Track A — Backend

### Fase A.1 — Fundação: schema, config, app e contratos *(tamanho L)*

- **id:** `A.1`
- **slug:** `foundation`
- **Objetivo:** fazer `docker compose up --build` subir de verdade, com banco inicializado, app respondendo através do nginx, e os contratos que os dois tracks vão consumir já fixados.
- **Depende de:** nenhuma
- **Arquivos novos:** `db/001_init.sql`, `backend/app/config.py`, `backend/app/main.py`, `backend/app/errors.py`, `backend/app/core/models.py`, `backend/app/adapters/db.py`, `backend/app/api/schemas.py`, `backend/tests/test_health.py`. **Arquivos alterados:** `backend/app/__init__.py`.
- **Passos:**
  1. `db/001_init.sql` com `CREATE EXTENSION IF NOT EXISTS vector`, as duas tabelas de §4 (incluindo `ON DELETE CASCADE` e o `unique (session_id, content_hash)`) e `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`.
  2. `config.py` com `pydantic-settings` cobrindo todas as variáveis do `.env.example`. `GEMINI_API_KEY` tem default `""` — a ausência é validada no adapter, não no import, senão nenhum teste roda sem chave.
  3. `core/models.py` com **todas** as dataclasses puras que as fases seguintes usam (`PageText`, `Chunk`, `DocumentStatus`), criado inteiro aqui para nenhuma fase posterior disputar o arquivo.
  4. `adapters/db.py`: pool `asyncpg` criado no lifespan **com retry e backoff por até ~30 s** — o Postgres pode aceitar conexão poucos instantes depois de o healthcheck passar.
  5. Ainda no lifespan: verificar que a dimensão da coluna `chunks.embedding` bate com `EMBEDDING_DIM` (`vector_dims` ou `atttypmod`) e abortar com mensagem clara se divergir; e marcar `failed` todo documento preso em `pending`/`processing`.
  6. `errors.py`: exceções de domínio com `code`, e handlers globais (inclusive para `RequestValidationError`) que serializam o envelope `{code, message}` de §4.
  7. `main.py`: app, lifespan, router montado com `prefix="/api"`, `GET /api/health` (com `SELECT 1`) e `GET /api/config`.
- **Testes:** `/api/health` responde `200`; `/api/config` devolve os três limites (AC-14); settings carregam defaults sem `.env`; o envelope de erro é aplicado a um erro de validação (AC-17).
- **Escopo travado / violações BLOQUEANTES:** não usar ORM nem query builder; não concatenar SQL; não expor `DATABASE_URL` nem chave em resposta ou log; não tornar `GEMINI_API_KEY` obrigatória no import; não criar rota de documento nesta fase; **não reintroduzir** nenhum dos seis defeitos da tabela de §4.
- **Critério de conclusão (gate):** `docker compose down -v && docker compose up --build`, **duas vezes seguidas a frio**, sobe os três serviços sem erro; `curl http://localhost:5173/api/health` responde `200` **através do nginx**; `make lint typecheck test` zero.

### Fase A.2 — Extração por página e chunking *(tamanho M)*

- **id:** `A.2`
- **slug:** `pdf-chunking`
- **Objetivo:** transformar bytes de PDF em chunks citáveis, com a página correta e sem cruzar fronteira.
- **Depende de:** `A.1`
- **Arquivos novos:** `backend/app/adapters/pdf.py`, `backend/app/core/chunking.py`, `backend/tests/test_pdf_extraction.py`, `backend/tests/test_chunking.py`. **Arquivos alterados:** nenhum.
- **Passos:**
  1. `extract_pages(data: bytes) -> list[PageText]` com `pypdf`, preservando o número base 1; invocado via `asyncio.to_thread` pelo chamador (é síncrono e CPU-bound).
  2. Validações que exigem parse — páginas contra `MAX_PDF_PAGES`, caracteres contra `MAX_EXTRACTED_CHARS`, zero caractere extraível — levantando exceções de domínio distintas de `errors.py`, cada uma com mensagem em pt-BR.
  3. `chunk_pages(pages, size, overlap) -> list[Chunk]` em `core/`: itera **página a página**, e a janela **reseta em cada página**. Corte em fronteira de parágrafo (`\n\n`), depois sentença, depois espaço; nunca no meio de palavra.
  4. `chunk_index` sequencial no documento inteiro; `page_number` da página que originou o chunk — inequívoco, porque o chunk vive dentro de uma página só.
  5. Normalizar espaços em branco excessivos sem destruir a fronteira de parágrafo.
- **Testes:** página correta e nenhum chunk multi-página (AC-6); determinismo (AC-6); corte não parte palavra e overlap mínimo respeitado (AC-7); página menor que a janela vira um chunk; excesso de páginas e PDF sem texto levantam a exceção certa (AC-4, AC-5).
- **Escopo travado / violações BLOQUEANTES:** `core/chunking.py` não pode importar `fastapi`, `asyncpg`, `google.genai` nem tocar I/O; não usar splitter de terceiros; não fazer OCR; não commitar PDF binário como fixture (gerar em código); não deixar um chunk cruzar fronteira de página.
- **Critério de conclusão (gate):** testes verdes rodando sem rede e sem banco; `make lint typecheck test` zero.

### Fase A.3 — Adapter Gemini de embeddings *(tamanho M)*

- **id:** `A.3`
- **slug:** `gemini-embeddings`
- **Objetivo:** converter textos em vetores respeitando o contrato de §4 e as restrições do free tier, sem vazar segredo.
- **Depende de:** `A.1`
- **Arquivos novos:** `backend/app/adapters/gemini.py`, `backend/scripts/check_embeddings.py`, `backend/tests/test_gemini_adapter.py`. **Arquivos alterados:** nenhum.
- **Passos:**
  1. **Antes de tudo:** escrever e rodar `scripts/check_embeddings.py` contra a API real, conforme a pré-condição de §4. Se o modelo devolver um vetor agregado em vez de N, embrulhar cada texto num objeto `Content` e rodar de novo até a asserção passar. Registrar o resultado em `backend/eval/README.md` na `FEAT-0002`.
  2. Protocolo `EmbeddingClient` com `embed_documents(texts) -> list[list[float]]` e `embed_query(text) -> list[float]`.
  3. Implementar com `google-genai`, em lotes de `EMBEDDING_BATCH_SIZE`, passando `task_type` e `output_dimensionality` conforme §4.
  4. Normalizar L2 todo vetor retornado, antes de entregar.
  5. Backoff exponencial com jitter para transitório e `429`, teto de tentativas configurável; `400` de payload é permanente e não repete.
  6. Sanitizar toda exceção propagada para que nenhum fragmento de chave apareça.
- **Testes:** `ceil(N/B)` requisições (AC-8); `429` aciona backoff e conclui, `400` não repete (AC-9); norma L2 = 1,0 e `task_type` diferentes entre os dois métodos (AC-10); chave nunca aparece na exceção (AC-13). Todos com cliente falso — nenhum teste chama a API real.
- **Escopo travado / violações BLOQUEANTES:** não logar a chave nem fragmento; não fazer uma requisição por chunk; não usar `except Exception` sem reclassificar; não deixar retry infinito; **não implementar pool de chaves** (cortado — os limites do free tier são por projeto, não por chave).
- **Critério de conclusão (gate):** `check_embeddings.py` passou contra a API real e o resultado está registrado; testes verdes sem rede; `make lint typecheck test` zero.

### Fase A.4 — Pipeline de ingestão e rotas *(tamanho L)*

- **id:** `A.4`
- **slug:** `ingestion-pipeline`
- **Objetivo:** amarrar upload, extração, chunking, embeddings e persistência numa máquina de estados consultável.
- **Depende de:** `A.2`, `A.3`
- **Arquivos novos:** `backend/app/adapters/repository.py`, `backend/app/ingestion.py`, `backend/app/api/documents.py`. **Arquivos alterados:** `backend/app/main.py`, `backend/app/api/schemas.py`.
- **Passos:**
  1. Protocolo `DocumentRepository` e implementação com SQL parametrizado: criar documento, buscar por `(session_id, content_hash)`, atualizar estado e progresso, inserir chunks em lote, ler estado.
  2. `POST /api/documents`: checar `Content-Length` contra `MAX_UPLOAD_MB` **antes** de ler o corpo (`413`); ler em pedaços com corte rígido no limite; conferir assinatura `%PDF` (`422`); calcular SHA-256 e, se já existir na sessão, devolver o documento existente (FR-12); senão persistir em `pending`, agendar `BackgroundTasks` passando **`bytes`** (não o `UploadFile`) e responder `202`.
  3. Pipeline: `processing` → `extract_pages` via `asyncio.to_thread` (uma extração só, reusada) → validações de FR-3 → chunking → embeddings em lotes, atualizando `chunks_processed` a cada lote → `ready`.
  4. Semáforo global de concorrência 1 em torno da ingestão (NFR-8).
  5. Toda exceção de domínio vira `failed` com a mensagem correspondente; `try/finally` garante que nenhum caminho deixa o documento em `processing`.
  6. `GET /api/documents/{id}` devolvendo o payload de §4; `404` com `code: "nao_encontrado"`.
  7. Gravar `session_id` do header `X-Session-Id` (sem usá-lo para autorização).
- **Testes:** upload responde rápido em `pending` (AC-1); limites da requisição recusados com o envelope certo (AC-2, AC-3); violações de parse terminam `failed` (AC-4, AC-5); progresso monotônico observável (AC-12); falha permanente vira `failed` sem vazar chave (AC-13); reenvio idêntico não reprocessa (AC-15).
- **Escopo travado / violações BLOQUEANTES:** nenhuma chamada ao Gemini fora do adapter da `A.3`; nenhum SQL concatenado; não deixar documento preso em `processing`; não parsear o PDF duas vezes; não bloquear o event loop com `pypdf`; não implementar retrieval nem chat.
- **Critério de conclusão (gate):** upload real do `Exemplo-YAITEC.pdf` chega a `ready` com chunks embedados; o índice HNSW é o de cosseno (AC-11); `make lint typecheck test` zero.

### Fase A.5 — Testes de ingestão *(tamanho M)*

- **id:** `A.5`
- **slug:** `ingestion-tests`
- **Objetivo:** provar o fluxo do backend de forma determinística e **offline**, com um único teste opcional contra banco real.
- **Depende de:** `A.4`
- **Arquivos novos:** `backend/tests/conftest.py`, `backend/tests/fakes.py`, `backend/tests/test_ingestion_api.py`, `backend/tests/test_ingestion_db.py`. **Arquivos alterados:** `backend/pyproject.toml` (marker `db` e `addopts = "-m 'not db'"`).
- **Passos:**
  1. `FakeEmbeddingClient` determinístico (vetor derivado de hash, normalizado) implementando o protocolo da `A.3`.
  2. `FakeRepository` em memória implementando o protocolo da `A.4` — é ele que torna a suíte offline de verdade, sem Postgres.
  3. Injetar os dois por override de dependência do FastAPI.
  4. Testar o fluxo `upload → estado → ready → chunks registrados` contra os fakes, mais as recusas e a falha de provedor.
  5. Cobrir AC-12 chamando a função de pipeline diretamente com um fake que registra as chamadas de progresso — pela rota é inobservável, porque a `BackgroundTasks` do Starlette termina antes de o cliente de teste retornar.
  6. `test_ingestion_db.py` marcado `@pytest.mark.db` para AC-11 (índice HNSW e colunas reais), excluído do `make test` e rodado por `make test-db` com o compose no ar.
- **Testes:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-12, AC-13, AC-15, AC-17 offline; AC-11 sob o marker `db`.
- **Escopo travado / violações BLOQUEANTES:** nenhum teste do `make test` pode exigir rede, banco ou `GEMINI_API_KEY`; nenhum `skip` ou `retry` para mascarar flakiness; não testar implementação privada quando a rota cobre o comportamento.
- **Critério de conclusão (gate):** `make test` verde **sem `GEMINI_API_KEY` e sem o compose no ar**; `make test-db` verde com o compose no ar; `make lint typecheck` zero.

### Track B — Frontend

### Fase B.1 — Bootstrap do app *(tamanho M)*

- **id:** `B.1`
- **slug:** `app-shell`
- **Objetivo:** React rodando dentro do container, com Tailwind, cliente HTTP alinhado ao envelope de erro e identidade de sessão.
- **Depende de:** nenhuma
- **Arquivos novos:** `frontend/index.html`, `frontend/src/{main.tsx,App.tsx,index.css}`, `frontend/src/lib/{api,session,types,errors,config}.ts`, `frontend/eslint.config.js`. **Arquivos alterados:** nenhum — `vite.config.ts`, `tsconfig.json` e `nginx.conf` já servem como estão.
- **Passos:**
  1. `index.html` e `main.tsx` montando o `App`; Tailwind 4 via `@import "tailwindcss"` em `index.css`.
  2. `session.ts`: UUID de `localStorage`, gerado com `crypto.randomUUID()` na primeira visita.
  3. `api.ts`: wrapper de `fetch` com base `/api`, header `X-Session-Id`, e normalização de erro que lê o envelope `{code, message}` de §4 — **com fallback para resposta não-JSON**, porque um proxy pode responder HTML.
  4. `errors.ts`: mapa de `code` → mensagem em pt-BR e ação sugerida. Mapear **por `code`, nunca por status**.
  5. `types.ts`: tipos espelhando o contrato de §4, escrito a partir da spec (não de `schemas.py`, que pode não existir ainda).
  6. `config.ts`: busca `GET /api/config` no boot e expõe os limites; sem constantes duplicadas e sem env de build.
  7. `eslint.config.js` (flat config) para `npm run lint` funcionar.
- **Testes:** `npx tsc --noEmit` e `npm run lint` zero; a página é servida pelo container em `localhost:5173`.
- **Escopo travado / violações BLOQUEANTES:** não instalar biblioteca de estado nem UI kit — React e Tailwind bastam; não hardcodar URL absoluta de backend; não duplicar limites do servidor no cliente; não afrouxar `strict`.
- **Critério de conclusão (gate):** `docker compose up --build` serve a página; lint e typecheck zero.

### Fase B.2 — Tela de upload *(tamanho M)*

- **id:** `B.2`
- **slug:** `upload-view`
- **Objetivo:** enviar um PDF com validação local coerente com o servidor e feedback de envio.
- **Depende de:** `B.1`, `A.4`
- **Arquivos novos:** `frontend/src/components/UploadDropzone.tsx`, `frontend/src/hooks/useUpload.ts`. **Arquivos alterados:** `frontend/src/App.tsx`.
- **Passos:**
  1. Dropzone com clique e arrastar-soltar, aceitando só `application/pdf`.
  2. Validar extensão e tamanho contra os limites de `config.ts` (vindos da API), com mensagem em pt-BR.
  3. `useUpload` enviando `FormData` no campo `file`, com **indicador indeterminado** durante o envio — `fetch` não reporta progresso de upload, e a barra que importa é a de processamento.
  4. Exibir nome e tamanho do arquivo escolhido.
  5. Ao receber `202`, guardar o id e passar o controle para o acompanhamento; **persistir o id em `localStorage`** para sobreviver a um recarregamento.
- **Testes:** envio válido transita para acompanhamento (AC-18); arquivo acima do limite é bloqueado antes da requisição (AC-18).
- **Escopo travado / violações BLOQUEANTES:** validação no cliente não substitui a do servidor; não aceitar outros formatos; não prometer barra de progresso de upload; textos em pt-BR e identificadores em inglês.
- **Critério de conclusão (gate):** upload de ponta a ponta **através do `docker compose`**, não do dev server; lint e typecheck zero.

### Fase B.3 — Acompanhamento e estados de erro *(tamanho M)*

- **id:** `B.3`
- **slug:** `processing-status`
- **Objetivo:** mostrar honestamente o que acontece durante o processamento e tornar toda falha acionável.
- **Depende de:** `B.2`
- **Arquivos novos:** `frontend/src/components/{ProcessingStatus,ErrorBanner}.tsx`, `frontend/src/hooks/useDocumentStatus.ts`. **Arquivos alterados:** `frontend/src/App.tsx`, `frontend/src/components/UploadDropzone.tsx`.
- **Passos:**
  1. `useDocumentStatus` com polling (intervalo mínimo 1 s), parando em `ready` ou `failed`, limpando o timer ao desmontar.
  2. Renderizar os quatro estados com rótulo em pt-BR e barra derivada de `chunks_processed / chunks_total`; indeterminado enquanto `chunks_total` é desconhecido.
  3. Ao montar, se houver id em `localStorage`, retomar o acompanhamento — recarregar a página não perde o documento.
  4. Banner de erro consumindo `errors.ts`, com a ação sugerida (tentar de novo, escolher outro arquivo).
  5. Estado vazio inicial com instrução clara; foco e rótulos acessíveis nos controles.
  6. Ao chegar em `ready`, sinalizar que o documento está pronto para conversa (consumido pela `FEAT-0002`).
- **Testes:** transição visível sem recarregar (AC-19); progresso monotônico na barra (AC-12); erro `limite_de_uso` vira mensagem com ação (AC-20); documento `failed` mostra a mensagem do backend (AC-5).
- **Escopo travado / violações BLOQUEANTES:** nunca exibir stack trace, corpo bruto ou nome de exceção; nunca exibir chave; não usar `alert()`; não deixar timer órfão; não inventar progresso que o backend não informou.
- **Critério de conclusão (gate):** ciclo `upload → processando → pronto` observável no compose, e sobrevivendo a um `F5`; lint e typecheck zero.

## 6. Riscos

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| 1 | O modelo de embedding devolver vetor agregado em vez de N vetores | Média | Alto | Pré-condição verificada contra a API real no primeiro passo da `A.3`, antes de qualquer código de pipeline |
| 2 | Quota do free tier estourar durante a avaliação | Média | Médio | Limites conservadores por env, lote de 16, backoff, dedup por hash, semáforo; `429` vira mensagem clara |
| 3 | `init.sql` não reaplicar após mudança de schema (só roda em banco vazio) | Alta | Médio | Documentado no README e no `Makefile` (`make stop` preserva, `make down` destrói); a `A.1` fixa o schema inteiro de uma vez |
| 4 | `BackgroundTasks` perder o processamento num restart | Média | Baixo | Varredura de órfãos no lifespan marca `failed` com orientação (FR-13) — o usuário vê o que houve em vez de barra eterna |
| 5 | PDF com layout complexo produzir texto embaralhado | Média | Médio | Validado com o `Exemplo-YAITEC.pdf` na `A.2` |
| 6 | Tracks divergirem no contrato de API | Baixa | Médio | §4 é a fonte única, escrita antes das duas fases; `types.ts` é derivado da spec, não de `schemas.py` |
| 7 | Regressão em um dos seis defeitos de infraestrutura corrigidos | Baixa | Alto | Tabela em §4 e escopo travado da `A.1`; o gate exige `up --build` a frio duas vezes e `curl` **através do nginx** |

## 7. Rollout

Sem produção e sem flag: a entrega é o repositório privado com `docker compose up`.

`A.1` primeiro — é ela que faz o compose subir e fixa os contratos que os dois tracks consomem. Depois `A.2` e `A.3` correm em paralelo (ambas dependem só de `A.1`). `A.4` amarra; `A.5` fecha os testes.

No Track B, `B.1` pode ser feita a qualquer momento, inclusive antes de `A.1`. `B.2` é o primeiro ponto de acoplamento (depende de `A.4`).

Rollback é `git revert` da fase. Mudança de schema exige `make down` antes do próximo `up`.

## 8. Open Questions

- **OQ-1 — Estratégia de chunking.** **RESOLVIDO (2026-08-17):** por página, sem cruzar fronteira, com janela de 500 caracteres e overlap de 100 dentro da página. *Justificativa:* torna a citação exata por construção — o avaliador confere a página contra o PDF dele. Também eleva o PDF de exemplo de ~4 para ~10 chunks, fazendo o `RETRIEVAL_TOP_K=5` da `FEAT-0002` selecionar de fato em vez de devolver o documento inteiro. *Rejeitado:* janela deslizante contínua com a página do início do chunk (citação errada quando cruza fronteira) e chunk por página inteira (grosso demais para caber num chip de citação).
- **OQ-5 — Processamento síncrono ou assíncrono.** **RESOLVIDO (2026-08-17):** `BackgroundTasks` com máquina de estados por polling. *Justificativa:* 20 páginas levam ~40 s só de embedding, além de qualquer timeout de request; e o desafio pede "mostre ao usuário que está processando". *Rejeitado:* processamento síncrono. *Verificado na revisão:* `BackgroundTasks` não é morto pelo FastAPI em tarefas dessa duração, e o `UploadFile` continuaria legível — ainda assim passamos `bytes`, por clareza e para não depender desse detalhe.
- **OQ-7 — Limites do PDF.** **RESOLVIDO (2026-08-17):** `MAX_UPLOAD_MB=25` protegendo upload e memória; `MAX_PDF_PAGES=20` e `MAX_EXTRACTED_CHARS=60000` protegendo a quota. *Justificativa:* megabyte é proxy ruim de custo de embedding — PDF de imagens pesa muito e custa pouco; texto denso pesa pouco e custa caro. Os limites de página e caracteres foram baixados de 50/200k na revisão, porque 200k caracteres já seriam ~1,7 min só de quota, sem contar backoff. *Rejeitado:* limite único em MB.
- **OQ-8 — Pool de chaves Gemini.** **RESOLVIDO (2026-08-17): cortado.** *Justificativa:* os limites do free tier são por projeto, não por chave — o recurso não faria nada com as chaves disponíveis, e custava código, teste, critério de aceite, variável de ambiente e documentação. *Rejeitado:* manter como recurso opcional.
- **OQ-9 — Modelo e dimensão do embedding.** **RESOLVIDO (2026-08-17):** `gemini-embedding-001`, `output_dimensionality=768`, normalização L2 manual, `task_type` assimétrico, índice `vector_cosine_ops`. *Justificativa:* o default de 3072 dimensões faria o `CREATE INDEX ... USING hnsw` abortar dentro do `docker-entrypoint-initdb.d` (o pgvector não indexa acima de 2000), derrubando o compose a frio; e sem opclass o índice nem compila. *Rejeitado:* deixar a decisão para a fase do adapter, como estava — o custo de descobrir tarde é `make down`, reingestão e quota queimada. *Consequência aceita:* `EMBEDDING_DIM` deixa de ser configurável na prática (um `.sql` não interpola variável) e o lifespan valida a coerência.

## 9. Definition of Done (gate por etapa)

**Gate por fase:**

- [ ] `A.1 foundation` — compose sobe a frio duas vezes; `/api/health` responde `200` através do nginx; envelope de erro aplicado.
- [ ] `A.2 pdf-chunking` — chunking por página, determinístico, testado sem rede e sem banco.
- [ ] `A.3 gemini-embeddings` — pré-condição verificada contra a API real; lote, backoff, `task_type` e normalização L2 testados com fake.
- [ ] `A.4 ingestion-pipeline` — `Exemplo-YAITEC.pdf` chega a `ready` com chunks embedados e índice de cosseno.
- [ ] `A.5 ingestion-tests` — `make test` verde sem chave e sem banco; `make test-db` verde com o compose no ar.
- [ ] `B.1 app-shell` — página servida pelo container; lint e typecheck zero.
- [ ] `B.2 upload-view` — upload de ponta a ponta pelo compose.
- [ ] `B.3 processing-status` — transição visível, sobrevivendo a `F5`; erros acionáveis em pt-BR.

**Itens globais transversais:**

- [ ] Cada FR tem ao menos um AC verificado.
- [ ] `make lint`, `make typecheck` e `make test` retornam zero, com `make test` rodando offline.
- [ ] Nenhum módulo de `backend/app/core/` importa `fastapi`, `asyncpg` ou `google.genai`.
- [ ] Nenhuma dependência de framework de RAG foi adicionada.
- [ ] Nenhuma chave de API, `DATABASE_URL` ou PII em log, resposta de erro ou arquivo versionado.
- [ ] Todo SQL é parametrizado.
- [ ] Identificadores em inglês; textos de UI e mensagens de erro em pt-BR.
- [ ] `docker compose up --build` de clone limpo sobe tudo e a tela de upload responde em `localhost:5173`.
- [ ] `.env.example` documenta toda variável que `config.py` lê — sem sobra e sem falta.
- [ ] Nenhum dos seis defeitos de infraestrutura de §4 voltou.
