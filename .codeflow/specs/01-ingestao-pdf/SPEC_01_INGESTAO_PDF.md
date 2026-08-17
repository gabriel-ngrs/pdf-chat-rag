---
id: FEAT-0001
slug: 01-ingestao-pdf
title: "Ingestão de PDF: fundação, extração por página, chunking, embeddings, vector store e design system"
type: feature
status: done
priority: P0
size: L
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

# FEAT-0001 — Ingestão de PDF e fundação do projeto

> **Nota de planning (2026-08-17, revisão 3):** esta spec passou por revisão adversarial de cinco revisores e por uma auditoria de rastreabilidade. Os seis defeitos de infraestrutura encontrados **já estão corrigidos no repositório** (§4.1) e são pré-condição, não trabalho. Esta revisão acrescenta o que o owner definiu como indispensável e não estava especificado: **design system de verdade** (via shadcn/ui, não CSS artesanal), **logging estruturado**, **testes de arquitetura executáveis** e **validação de segurança**. Cada fase agora traz o *porquê* e o contexto que um agente em sessão zerada precisa para executá-la sem reabrir decisões.
>
> **Fora do escopo:** chat, retrieval e geração (`FEAT-0002`); biblioteca de múltiplos documentos (cortada — ver `.codeflow/decisions/2026-08-17-revisao-adversarial-das-specs.md`); autenticação e autorização; formatos além de PDF; OCR; deploy e CI; observabilidade com métricas e tracing.

## Resumo executivo (TL;DR)

| | |
|---|---|
| **O quê** | A pessoa envia um PDF; o backend extrai o texto página a página, quebra em chunks que nunca cruzam fronteira de página, gera embeddings e persiste no pgvector, com o estado visível e registrado em log estruturado. |
| **Por quê** | É o requisito 1 do desafio e a fundação de tudo: sem chunks embedados e citáveis por página, não existe RAG fundamentado. E é aqui que nascem a arquitetura, os gates e o design system que a `FEAT-0002` vai consumir. |
| **Backend-Infra** | Schema com `vector(768)` e índice HNSW de cosseno; logging JSON com `request_id`; envelope de erro único; upload assíncrono com máquina de estados; adapter Gemini com lote, backoff, `task_type` e normalização L2. |
| **Frontend** | Design system sobre shadcn/ui, sistema de avisos ao usuário, tela de upload com limites lidos da API e acompanhamento do processamento. |
| **Qualidade** | `make check` agrega lint, typecheck, **teste de arquitetura** (`import-linter`) e suíte offline; `make security` roda bandit, pip-audit e npm audit. |
| **Tamanho** | L — 6 fases no Track A (backend) e 4 no Track B (frontend). |

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

O desafio da YAITEC pede um app onde a pessoa envia um PDF e conversa com ele, com respostas fundamentadas citando trecho ou página. Antes de qualquer conversa, o documento precisa virar dado consultável por similaridade.

**O detalhe que decide a nota está na extração.** Se o PDF virar um texto único e só depois for cortado, o número da página se perde e citar vira adivinhação. Extrair por página e **nunca deixar um chunk cruzar a fronteira** faz a citação ser exata por construção — e o avaliador vai conferir contra um PDF de 3 páginas que ele mesmo enviou.

**As quotas do free tier ditaram a arquitetura.** O gargalo medido é o TPM de embeddings (~30.000 tokens/min). Um documento no teto desta spec (20 páginas, 60.000 caracteres, ~16k tokens) leva por volta de 40 segundos só embedando. Nenhum request HTTP sobrevive a isso — daí o processamento assíncrono e o estado visível. "Mostre ao usuário que está processando" é consequência da quota, não enfeite.

**Esta spec também é onde a qualidade do projeto é estabelecida.** Três coisas que o owner definiu como indispensáveis e que não existiam no plano anterior:

- **Interface.** O eixo Produto/UX é um terço da avaliação, e "cobrir estados de erro" não é UX. A fase `B.1` monta um design system real sobre shadcn/ui em vez de improvisar CSS — decisão do owner, que revisa e ajusta depois.
- **Logs.** Um sistema que não conta o que fez é impossível de diagnosticar. O logging estruturado nasce na `A.1` e acompanha cada etapa da ingestão.
- **Gates executáveis.** "`core/` não importa I/O" era um princípio escrito; vira um teste que falha o build (`make arch`). O mesmo para segurança: `bandit` no código e testes que provam que a chave nunca vaza.

### 1.1 Princípios invioláveis

Itens 1–5 vêm de `.codeflow/constitution.md`, versionada neste repositório. Itens 6–9 vêm das rules universais do framework codeflow do autor (`~/.codeflow/framework/core/rules/`), que não são versionadas aqui — o README declara isso.

1. **`backend/app/core/` não importa `fastapi`, `asyncpg` nem `google.genai`.** — `constitution.md`, `## Regras invariantes específicas`. **Agora verificável por `make arch`.**
2. **Frameworks de RAG são proibidos** (`langchain`, `llama-index` e equivalentes fora das dependências). — idem.
3. **Segredos só em variável de ambiente, nunca em log ou mensagem de exceção.** — idem, e rule `security`. **Agora verificável por teste.**
4. **`mypy --strict` e `tsc` strict retornam zero; nenhum gate é afrouxado.** — idem.
5. **De um clone limpo, `docker compose up --build` sobe a aplicação inteira.** — idem, `## Áreas de alto risco`.
6. **Toda entrada externa é validada no servidor; validação no cliente é conveniência.** — rule `security`.
7. **SQL parametrizado; nunca concatenação com input externo.** — rule `security`.
8. **Identificadores em inglês; textos ao usuário em pt-BR.** — rule `naming`.
9. **Todo código novo tem teste; teste descreve comportamento e é determinístico.** — rule `testing`.

## 2. Requisitos

### Funcionais

- **FR-1** — `POST /api/documents` aceita upload multipart (campo `file`) de um PDF e responde `202` com `{id, status}` sem aguardar o processamento.
- **FR-2** — Na requisição, antes de ler o corpo inteiro, o servidor rejeita `Content-Length` acima de `MAX_UPLOAD_MB` (`413`) e arquivo cuja assinatura não comece por `%PDF` (`422`). A leitura é cortada rigidamente no limite.
- **FR-3** — Tudo que exige parse do PDF — páginas contra `MAX_PDF_PAGES`, caracteres contra `MAX_EXTRACTED_CHARS`, ausência de texto extraível — é validado **no background** e resulta em `failed` com mensagem em pt-BR específica.
- **FR-4** — A extração produz o texto de cada página com seu número (base 1) e roda fora do event loop.
- **FR-5** — O chunking é determinístico e **por página**: nenhum chunk cruza fronteira. Dentro da página, janela de `CHUNK_SIZE` com `CHUNK_OVERLAP`, cortando em fronteira de parágrafo, depois sentença, depois espaço — nunca no meio de palavra.
- **FR-6** — Embeddings em lote de até `EMBEDDING_BATCH_SIZE`, com `task_type=RETRIEVAL_DOCUMENT`, `output_dimensionality=EMBEDDING_DIM` e normalização L2. Transitório e `429` acionam backoff exponencial com jitter; `400` de payload é permanente e não repete.
- **FR-7** — O adapter expõe `embed_query`, com `task_type=RETRIEVAL_QUERY` e a mesma normalização — implementado e testado aqui, consumido pela `FEAT-0002`.
- **FR-8** — Documento e chunks persistidos no Postgres; vetor em `vector(768)` com índice `USING hnsw (embedding vector_cosine_ops)`.
- **FR-9** — O documento percorre `pending → processing → ready → failed`. Toda saída de erro grava `failed`; nenhum caminho deixa o documento preso em `processing`.
- **FR-10** — `GET /api/documents/{id}` devolve estado, `chunks_processed`, `chunks_total`, `page_count` e `error_message`.
- **FR-11** — `GET /api/config` devolve os limites vigentes, para o cliente validar contra os mesmos números sem duplicá-los.
- **FR-12** — Upload do mesmo conteúdo (mesmo SHA-256) na mesma sessão devolve o documento existente em vez de reprocessar.
- **FR-13** — No startup, documentos presos em `pending`/`processing` são marcados `failed` com mensagem orientando reenviar.
- **FR-14** — Todo erro da API usa o envelope `{"code": "<slug>", "message": "<pt-BR>"}`, inclusive os de validação do framework, via handler global.
- **FR-15** — O sistema emite **log estruturado em JSON** com `timestamp`, `level`, `event`, `request_id` e o contexto do domínio (`document_id`, `chunk_count`, `duration_ms`). Cada etapa da ingestão emite um evento nomeado. Nenhum log contém chave de API, `DATABASE_URL` ou o conteúdo do PDF.
- **FR-16** — A UI tem um **sistema de avisos** com três níveis (informação, sucesso, erro), um único componente responsável, e mensagem sempre acionável em pt-BR.
- **FR-17** — A tela de upload permite selecionar ou arrastar um PDF, valida extensão e tamanho contra `GET /api/config` e mostra indicador de envio.
- **FR-18** — A UI acompanha `GET /api/documents/{id}` e exibe o estado com progresso derivado de `chunks_processed / chunks_total`, até `ready` ou `failed`, sem recarregar.
- **FR-19** — A interface é construída sobre um **design system** (shadcn/ui + tokens do projeto), com tema claro e escuro, tipografia e espaçamento definidos, e layout utilizável em tela estreita.

### Não-funcionais

- **NFR-1** — O progresso é atualizado a cada lote de embeddings, no máximo a cada 15 segundos.
- **NFR-2** — `backend/app/core/` não importa `fastapi`, `asyncpg` nem `google.genai`, e isso é verificado automaticamente.
- **NFR-3** — Nenhuma chave de API aparece em log, resposta ou mensagem de exceção.
- **NFR-4** — `make check` (lint + typecheck + arch + test) retorna zero, e `make test` roda **sem `GEMINI_API_KEY` e sem banco**.
- **NFR-5** — De um clone limpo com `.env` preenchido, `docker compose up --build` sobe os três serviços e a tela responde em `http://localhost:5173`.
- **NFR-6** — Limites, ids de modelo e parâmetros de chunking são configuráveis por env. **A dimensão do vetor é exceção declarada:** vive fixa no DDL, e o lifespan valida a coerência.
- **NFR-7** — O upload não bloqueia o event loop.
- **NFR-8** — Uma ingestão por vez (semáforo global).
- **NFR-9** — Todo módulo e toda função pública de `core/` e `adapters/` tem docstring dizendo **o que faz e por quê**, não como.
- **NFR-10** — A cobertura de testes de `backend/app/core/` é de no mínimo 90%, verificada no gate.
- **NFR-11** — `make security` (bandit + pip-audit + npm audit) retorna zero achados de severidade alta.
- **NFR-12** — Os controles interativos são operáveis por teclado e têm rótulo acessível; o contraste de texto atende AA.

## 3. Critérios de aceite

- **AC-1** (FR-1, NFR-7) — *Dado* um PDF válido de 3 páginas, *quando* faço `POST /api/documents`, *então* recebo `202` com `{id, status:"pending"}` em menos de 2 s e o processamento segue em background.
- **AC-2** (FR-2) — *Dado* um arquivo de 30 MB com `MAX_UPLOAD_MB=25`, *quando* faço o upload **através do nginx**, *então* recebo `413` com corpo JSON `{code:"arquivo_grande", message}` — não HTML do nginx.
- **AC-3** (FR-2) — *Dado* um `.txt` renomeado para `.pdf`, *quando* faço o upload, *então* recebo `422` com `code:"arquivo_invalido"`.
- **AC-4** (FR-3) — *Dado* um PDF com 40 páginas e `MAX_PDF_PAGES=20`, *quando* o processamento roda, *então* o documento termina `failed` citando o limite de páginas.
- **AC-5** (FR-3) — *Dado* um PDF sem camada de texto, *então* termina `failed` explicando que não há texto extraível e que OCR não é suportado.
- **AC-6** (FR-4, FR-5) — *Dado* um texto de duas páginas conhecidas, *quando* rodo extração e chunking, *então* cada chunk carrega o número correto, **nenhum chunk contém texto de duas páginas**, e duas execuções produzem resultado idêntico.
- **AC-7** (FR-5) — *Dado* uma página maior que a janela, *então* nenhum chunk começa ou termina no meio de palavra, e chunks consecutivos da mesma página compartilham ao menos `CHUNK_OVERLAP // 2` caracteres.
- **AC-8** (FR-6) — *Dado* N chunks e `EMBEDDING_BATCH_SIZE=B`, *então* o adapter faz exatamente `ceil(N/B)` requisições.
- **AC-9** (FR-6) — *Dado* `429` na primeira chamada, *então* o adapter espera com backoff e conclui; *dado* `400` de payload, *então* não repete e falha com mensagem própria.
- **AC-10** (FR-6, FR-7) — *Dado* um vetor retornado, *então* sua norma L2 é 1,0 (tolerância 1e-6), e `embed_documents` e `embed_query` usam `task_type` diferentes.
- **AC-11** (FR-8) — *Dado* um documento processado, *então* cada linha de `chunks` tem `document_id`, `page_number`, `chunk_index`, `content` e `embedding` não nulo, e o índice HNSW é `vector_cosine_ops`.
- **AC-12** (FR-9, FR-10, NFR-1) — *Dado* um upload em andamento, *então* observo `pending → processing → ready` com `chunks_processed` crescendo monotonicamente até `chunks_total`.
- **AC-13** (FR-9, NFR-3) — *Dado* falha permanente do provedor, *então* o documento fica `failed` com mensagem em pt-BR e nenhuma chave aparece nela.
- **AC-14** (FR-11) — *Dado* que chamo `GET /api/config`, *então* recebo os três limites com os mesmos valores que o servidor aplica.
- **AC-15** (FR-12) — *Dado* que envio o mesmo PDF duas vezes na mesma sessão, *então* o segundo devolve o documento existente e **nenhum embedding novo é gerado**.
- **AC-16** (FR-13) — *Dado* um documento em `processing` e um restart, *quando* o app sobe, *então* ele passa a `failed` com mensagem orientando reenviar.
- **AC-17** (FR-14) — *Dado* qualquer erro `4xx`/`5xx`, *então* o corpo tem exatamente `{code, message}` — inclusive nos erros de validação do framework.
- **AC-18** (FR-15) — *Dado* uma ingestão completa, *quando* leio os logs, *então* encontro eventos JSON nomeados para recebimento, extração, chunking, cada lote de embedding e conclusão, todos com o mesmo `request_id` e com `duration_ms`.
- **AC-19** (FR-15, NFR-3) — *Dado* uma `GEMINI_API_KEY` definida e qualquer caminho de erro exercitado, *quando* faço `grep` da chave na saída de log capturada, *então* não há ocorrência — verificado por teste automatizado.
- **AC-20** (FR-16, FR-17) — *Dado* que escolho um arquivo acima do limite lido de `GET /api/config`, *então* a UI bloqueia antes da requisição e mostra um aviso de erro em pt-BR com a ação sugerida.
- **AC-21** (FR-17) — *Dado* que arrasto um PDF válido, *então* vejo nome, tamanho e indicador de envio.
- **AC-22** (FR-18) — *Dado* um upload aceito, *então* a UI mostra "processando" com progresso e transita para "pronto" sem recarregar.
- **AC-23** (FR-19, NFR-12) — *Dado* a interface entregue, *então* ela usa os tokens do design system, funciona em tema claro e escuro, é utilizável a 375 px de largura, e todo controle é alcançável por `Tab` com rótulo acessível.
- **AC-24** (NFR-2) — *Dado* que alguém acrescente `import asyncpg` a um módulo de `core/`, *quando* rodo `make arch`, *então* o comando falha apontando o contrato violado.
- **AC-25** (NFR-4) — *Dado* nenhum `GEMINI_API_KEY` no ambiente e nenhum container no ar, *quando* rodo `make check`, *então* ele retorna zero.
- **AC-26** (NFR-5) — *Dado* um clone limpo com `.env` preenchido, *quando* rodo `docker compose up --build`, *então* os três serviços sobem e **`curl http://localhost:5173/api/health` responde `200` através do nginx**.
- **AC-27** (NFR-6) — *Dado* que `EMBEDDING_DIM` diverge da dimensão da coluna, *quando* o backend sobe, *então* ele falha rápido com mensagem clara.
- **AC-28** (NFR-8) — *Dado* dois uploads disparados ao mesmo tempo, *então* o segundo pipeline só começa depois que o primeiro termina.
- **AC-29** (NFR-9, NFR-10) — *Dado* o código entregue, *então* toda função pública de `core/` e `adapters/` tem docstring, e a cobertura de `core/` é ≥ 90%.
- **AC-30** (NFR-11) — *Dado* o código entregue, *quando* rodo `make security`, *então* não há achado de severidade alta em bandit, pip-audit ou npm audit.

## 4. Abordagem técnica

### 4.1 Estado corrigido do esqueleto (pré-condição, já aplicado)

Encontrados na revisão adversarial e **já corrigidos no repositório**. Nenhuma fase precisa refazê-los; qualquer um voltando é regressão bloqueante.

| Arquivo | O que estava errado | Correção |
|---|---|---|
| `frontend/nginx.conf` | `proxy_pass` com barra final removia o prefixo `/api` | barra removida |
| `frontend/nginx.conf` | sem `client_max_body_size`, o default de 1 MB recusava o upload com HTML | `client_max_body_size 30m` |
| `docker-compose.yml` | `pg_isready` sem `-h` fica verde pelo socket unix enquanto o TCP está fechado | `-h 127.0.0.1` + `start_period` |
| `docker-compose.yml` | sem `env_file`, só duas variáveis chegavam ao container | `env_file: .env`; `db` publica 5432 |
| `backend/Dockerfile` | `uv run` no CMD ressincronizava o grupo `dev` a cada start | binário do venv; `uv sync --frozen`; locks commitados |
| `backend/pyproject.toml` | `fastapi>=0.115` não tem SSE nativo | `>=0.135` (resolvido 0.141.1) |

### 4.2 Contrato de embedding (fixado)

| Item | Valor | Por quê |
|---|---|---|
| Modelo | `gemini-embedding-001` | text-only basta e é o que expõe `task_type` |
| Dimensão | **768** via `output_dimensionality` | o default é 3072 e o HNSW do pgvector aceita no máximo 2000 — `CREATE INDEX` abortaria dentro do initdb |
| Normalização | **L2 manual, obrigatória** | o modelo só entrega normalizado em 3072; sem normalizar, o cosseno mente |
| `task_type` | `RETRIEVAL_DOCUMENT` nos chunks, `RETRIEVAL_QUERY` na pergunta | mecanismo documentado do provedor para retrieval; custa um parâmetro |
| Índice | `USING hnsw (embedding vector_cosine_ops)` | sem opclass o `CREATE INDEX` nem compila; índice L2 não atende ao `<=>` da `FEAT-0002` |
| Lote | `EMBEDDING_BATCH_SIZE=16` | 100 chunks passariam do teto de tokens por requisição e consumiriam quase todo o TPM |

**Pré-condição verificada contra a API real, antes da `A.3`:** script que embeda `["gato", "cachorro", "mecânica quântica"]` e afirma `len(embeddings) == 3` e `cos(v0,v1) > cos(v0,v2)`. O motivo é específico: o comportamento de lote **difere entre modelos** do provedor — há modelo que devolve um único vetor agregado quando vários textos vão direto na lista. Nenhum teste offline detecta isso, porque o fake devolve N vetores para N textos; o sintoma seria retrieval retornando chunks aleatórios com a suíte verde.

### 4.3 Envelope de erro (fonte única dos dois tracks)

```json
{ "code": "arquivo_grande", "message": "O arquivo excede o limite de 25 MB." }
```

| `code` | Status | Quando |
|---|---|---|
| `arquivo_grande` | 413 | `Content-Length` acima de `MAX_UPLOAD_MB` |
| `arquivo_invalido` | 422 | assinatura não é `%PDF`, ou payload inválido |
| `nao_encontrado` | 404 | documento inexistente |
| `limite_de_uso` | 429 | quota do provedor |
| `erro_interno` | 500 | qualquer outra |

O frontend mapeia **por `code`, nunca por status** — é o que impede os tracks de divergirem e o que faz a mesma tabela valer na `FEAT-0002`.

### 4.4 Contrato de logging

`structlog` configurado para emitir JSON em produção. Campos obrigatórios em todo evento: `timestamp`, `level`, `event`, `request_id`. Middleware gera `request_id` (UUID4) por requisição e o injeta no contexto; a task de background herda o mesmo id, para a ingestão inteira ser rastreável numa linha de `grep`.

| `event` | Nível | Contexto adicional |
|---|---|---|
| `document.received` | info | `document_id`, `filename`, `size_bytes` |
| `document.duplicate` | info | `document_id`, `content_hash` |
| `document.extracted` | info | `document_id`, `page_count`, `char_count`, `duration_ms` |
| `document.chunked` | info | `document_id`, `chunk_count`, `duration_ms` |
| `embedding.batch` | debug | `document_id`, `batch_index`, `batch_size`, `duration_ms` |
| `embedding.retry` | warning | `document_id`, `attempt`, `reason` |
| `document.ready` | info | `document_id`, `chunk_count`, `total_duration_ms` |
| `document.failed` | error | `document_id`, `code`, `message` |
| `document.orphan_swept` | warning | `document_id` |

**Proibições de log:** chave de API, `DATABASE_URL`, conteúdo integral de chunk ou do PDF. Trechos de conteúdo, quando necessários para diagnóstico, são truncados em 80 caracteres.

### 4.5 Contrato de API

```
POST /api/documents        multipart: file  → 202 {"id","status"}
GET  /api/documents/{id}                    → 200 {"id","filename","status","page_count",
                                                   "chunks_total","chunks_processed","error_message"}
GET  /api/config                            → 200 {"max_upload_mb","max_pdf_pages","max_extracted_chars"}
GET  /api/health                            → 200 {"status":"ok","database":"ok"}
```

`status` ∈ `pending | processing | ready | failed`. `X-Session-Id` é enviado pelo cliente e gravado; **não é usado para autorização** nesta entrega — o README declara como organização por browser, não fronteira de segurança.

### 4.6 Modelo de dados

```sql
documents(id uuid pk default gen_random_uuid(), filename text not null,
          content_hash text not null, status text not null, error_message text,
          page_count int, chunks_total int, chunks_processed int not null default 0,
          session_id text, created_at timestamptz not null default now(),
          unique (session_id, content_hash))
chunks(id bigserial pk,
       document_id uuid not null references documents(id) on delete cascade,
       chunk_index int not null, page_number int not null,
       content text not null, embedding vector(768) not null)
```

`gen_random_uuid()` vem do `pgcrypto`, presente no PG16. O `ON DELETE CASCADE` é declarado por quem cria a tabela.

### 4.7 Design system (decisão do owner)

A interface é construída sobre **shadcn/ui** — componentes copiados para o projeto (não dependência de runtime opaca), sobre Radix para acessibilidade e Tailwind 4 para estilo. Verificado: shadcn/ui suporta Tailwind v4 e React 19, com o mesmo plugin Vite já configurado.

Motivo da escolha, e por que ela cabe aqui: CSS artesanal num prazo curto produz tela cinza funcional, e o eixo Produto/UX é um terço da nota. shadcn dá primitivos com acessibilidade resolvida (foco, teclado, ARIA) e um sistema de tokens em OKLCH pronto para tema claro/escuro. O owner revisa e ajusta detalhes depois.

Componentes previstos: `button`, `card`, `progress`, `scroll-area`, `separator`, `skeleton`, `sonner` (avisos), `tooltip`, `badge`, `dialog`. A `FEAT-0002` acrescenta o que o chat exigir.

### 4.8 Testes de arquitetura e de segurança

**Arquitetura** — `backend/.importlinter` declara contratos verificados por `make arch`:

1. *Camadas*: `app.api` → `app.adapters` → `app.core`, nesta direção. Camada de baixo não importa camada de cima.
2. *Núcleo puro*: `app.core` é proibido de importar `fastapi`, `asyncpg`, `google`, `structlog` e qualquer módulo de `app.adapters` ou `app.api`.
3. *Sem framework de RAG*: nenhum módulo importa `langchain` ou `llama_index`.

**Segurança** — `make security` roda `bandit -r app`, `pip-audit` e `npm audit --audit-level=high`. Além da análise estática, três testes de comportamento: chave nunca em log (AC-19), SQL parametrizado resistindo a input com aspas e `;`, e upload de arquivo com nome malicioso (`../../etc/passwd`) não escapando do escopo.

### 4.9 Mapa NOVO vs. REUSADO vs. REMOVIDO

**REUSADO** (existe e foi verificado): `db/` montado em `docker-entrypoint-initdb.d`; `backend/app/{core,adapters,api}/`, `backend/tests/`, `backend/eval/`; `backend/pyproject.toml` (já declara `fastapi`, `asyncpg`, `pypdf`, `google-genai`, `pydantic-settings`, `python-multipart`, `structlog`, e no grupo dev `pytest`, `ruff`, `mypy`, `import-linter`, `bandit`, `pip-audit`); `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/package.json`, `Makefile` (já tem os alvos `check`, `arch`, `security`, `eval`, `test-db`, `stop`), `.env.example`; `frontend/src/`.

**NOVO:** `db/001_init.sql`; `backend/.importlinter`; `backend/app/{config,logging_setup,errors,main,ingestion}.py`; `backend/app/core/{models,chunking}.py`; `backend/app/adapters/{db,pdf,gemini,repository}.py`; `backend/app/api/{documents,schemas,middleware}.py`; `backend/scripts/check_embeddings.py`; `backend/tests/*`; `frontend/components.json`; `frontend/src/components/ui/*` (gerados pelo CLI do shadcn); `frontend/src/{main.tsx,App.tsx,index.css}`; `frontend/index.html`; `frontend/src/lib/{utils,api,session,types,errors,config}.ts`; `frontend/src/components/{AppShell,UploadDropzone,ProcessingStatus}.tsx`; `frontend/src/hooks/{useUpload,useDocumentStatus}.ts`; `frontend/eslint.config.js`.

**REMOVIDO:** `db/.gitkeep`, `frontend/src/.gitkeep`, `backend/eval/.gitkeep` quando as pastas ganharem conteúdo.

### 4.10 Restrições de free tier e como o desenho responde

| Restrição | Efeito | Resposta |
|---|---|---|
| Embeddings ~30k TPM | 20 páginas ≈ 16k tokens ≈ ~40 s | processamento assíncrono + estado consultável |
| Teto de tokens por requisição | lote de 100 estouraria | `EMBEDDING_BATCH_SIZE=16` |
| Duas ingestões simultâneas | ambas caem em `429` | semáforo global (NFR-8) |
| Reenvio do mesmo PDF | queima quota à toa | dedup por `content_hash` (FR-12) |
| Números não oficiais | constante fixa envelhece | tudo por env + backoff independente do valor exato |

## 5. Plano de desenvolvimento por fases

> Cada fase é executável isoladamente por um agente lendo só este documento. Uma fase só inicia quando todas as listadas em "Depende de" estão concluídas. Os tracks A e B correm em paralelo; o acoplamento está declarado por `id`.

### Track A — Backend

### Fase A.1 — Fundação: schema, config, logging e contratos *(tamanho L; ≈3h)*

- **id:** `A.1`
- **slug:** `foundation`
- **Objetivo:** fazer `docker compose up --build` subir de verdade, com banco inicializado, app respondendo através do nginx, logging estruturado funcionando e os contratos que os dois tracks vão consumir já fixados.
- **Por que esta fase existe:** ela é a única que destrava todas as outras, e é onde ficam as três decisões caras de reverter — o DDL (só roda em banco vazio), o envelope de erro (consumido por dois tracks) e o formato de log (usado por todo o resto). Errar aqui custa `make down` e retrabalho; acertar aqui torna as fases seguintes mecânicas.
- **Depende de:** nenhuma
- **Contexto que o agente precisa:** o repositório é o esqueleto do `/bootstrap` com os seis defeitos de §4.1 **já corrigidos** — não refaça e não reverta. `backend/app/{core,adapters,api}/` existem e estão vazios (só `__init__.py`). `db/` está vazio. O `docker-compose.yml` monta `./db` em `docker-entrypoint-initdb.d` e o healthcheck do Postgres já usa `-h 127.0.0.1`. As variáveis de ambiente estão todas catalogadas em `.env.example` — `config.py` deve cobrir exatamente aquele conjunto, sem sobra e sem falta. O contrato de embedding de §4.2 é decisão fechada: a coluna é `vector(768)` e o índice é `vector_cosine_ops`, mesmo que nada consuma isso ainda.
- **Arquivos novos:** `db/001_init.sql`, `backend/.importlinter`, `backend/app/{config,logging_setup,errors,main}.py`, `backend/app/core/models.py`, `backend/app/adapters/db.py`, `backend/app/api/{schemas,middleware}.py`, `backend/tests/{test_health,test_config,test_errors}.py`. **Arquivos alterados:** `backend/app/__init__.py`.
- **Passos:**
  1. **`db/001_init.sql`** — `CREATE EXTENSION IF NOT EXISTS vector;`, as duas tabelas de §4.6 literalmente (com `ON DELETE CASCADE` e o `unique (session_id, content_hash)`), e `CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);`. *Por quê o opclass explícito:* sem ele o comando falha com `no default operator class`, e um índice L2 não seria usado pelo `<=>` de cosseno da `FEAT-0002`.
  2. **`config.py`** — `Settings(BaseSettings)` com todos os campos de `.env.example`, tipados. `GEMINI_API_KEY` tem default `""`. *Por quê:* se for obrigatória no import, `import app.main` explode sem `.env` e **nenhum teste roda**. A ausência é validada no adapter, no momento do uso.
  3. **`logging_setup.py`** — configurar `structlog` conforme §4.4: processadores de timestamp ISO, nível, nome do evento, e renderer JSON. Expor `configure_logging()` chamado no lifespan e `get_logger()`. *Por quê structlog e não `logging` puro:* o binding de contexto (`log.bind(document_id=...)`) é o que faz a ingestão inteira aparecer num `grep` por `request_id` sem repetir o campo em cada chamada.
  4. **`api/middleware.py`** — middleware que gera `request_id` (UUID4), o injeta no contexto do structlog e o devolve no header `X-Request-Id`. *Por quê o header:* permite ao avaliador correlacionar o que viu na tela com a linha de log.
  5. **`core/models.py`** — **todas** as dataclasses puras que as fases seguintes usam: `PageText(page_number, text)`, `Chunk(chunk_index, page_number, content)`, `DocumentStatus` como `StrEnum`. *Por quê criar tudo agora:* na versão anterior deste plano, `A.2` e `A.3` disputavam este arquivo declarando-se independentes; criar completo aqui elimina a colisão.
  6. **`errors.py`** — hierarquia `AppError(code, message, status)` com as subclasses de §4.3, mais handlers globais registrados no app: um para `AppError`, um para `RequestValidationError` (traduzindo para `arquivo_invalido`) e um para `Exception` (virando `erro_interno`, com o traceback no log e **não** na resposta).
  7. **`adapters/db.py`** — pool `asyncpg` criado no lifespan **com retry e backoff por até ~30 s**. *Por quê:* o healthcheck pode passar poucos instantes antes de o Postgres aceitar conexão TCP; sem retry o uvicorn morre num `up` a frio.
  8. **Ainda no lifespan, duas verificações:** (a) comparar a dimensão real da coluna `chunks.embedding` (`SELECT atttypmod` em `pg_attribute`, ou `vector_dims`) com `EMBEDDING_DIM`, abortando com mensagem clara se divergir; (b) marcar `failed` todo documento preso em `pending`/`processing`, emitindo `document.orphan_swept`.
  9. **`main.py`** — app, lifespan, middleware, router montado com `prefix="/api"`, `GET /api/health` (com `SELECT 1`) e `GET /api/config`.
  10. **`.importlinter`** — os três contratos de §4.8. Rodar `make arch` e confirmar que passa com a estrutura atual.
- **Testes:** `/api/health` responde `200` (AC-26); `/api/config` devolve os três limites (AC-14); settings carregam sem `.env`; erro de validação sai no envelope (AC-17); a verificação de dimensão aborta quando divergente (AC-27); a varredura marca órfão como `failed` (AC-16); `make arch` passa (AC-24).
- **Escopo travado / violações BLOQUEANTES:** não usar ORM nem query builder; não concatenar SQL; não expor `DATABASE_URL` nem chave em resposta ou log; **não tornar `GEMINI_API_KEY` obrigatória no import**; não criar rota de documento nesta fase; **não reintroduzir** nenhum defeito de §4.1; não emitir log em texto livre — todo log passa pelo `structlog` com evento nomeado.
- **Critério de conclusão (gate):** `docker compose down -v && docker compose up --build`, **duas vezes seguidas a frio**, sobe os três serviços sem erro; `curl http://localhost:5173/api/health` responde `200` **através do nginx** e o header `X-Request-Id` está presente; `make check` zero.

### Fase A.2 — Extração por página e chunking *(tamanho M; ≈2h)*

- **id:** `A.2`
- **slug:** `pdf-chunking`
- **Objetivo:** transformar bytes de PDF em chunks citáveis, com a página correta e sem cruzar fronteira.
- **Por que esta fase existe:** é aqui que a citação nasce. Todo o eixo de fundamentação da `FEAT-0002` depende de o `page_number` de um chunk ser verdadeiro — e a única forma de garantir isso sem heurística é o chunk nunca conter texto de duas páginas.
- **Depende de:** `A.1`
- **Contexto que o agente precisa:** `core/models.py` já tem `PageText` e `Chunk` — use, não redefina. As exceções de domínio já existem em `errors.py` — acrescente as específicas de PDF ali, não crie hierarquia nova. `pypdf` é síncrono e CPU-bound: esta fase **não** chama `asyncio.to_thread`, mas documenta na docstring que o chamador deve fazê-lo (quem chama é a `A.4`). O PDF de exemplo do desafio tem 3 páginas e ~1.220 caracteres por página, então com `CHUNK_SIZE=500` cada página vira 2 a 3 chunks — é esse número que faz o `RETRIEVAL_TOP_K=5` da `FEAT-0002` selecionar de fato em vez de devolver o documento inteiro.
- **Arquivos novos:** `backend/app/adapters/pdf.py`, `backend/app/core/chunking.py`, `backend/tests/{test_pdf_extraction,test_chunking}.py`, `backend/tests/factories.py`. **Arquivos alterados:** `backend/app/errors.py`.
- **Passos:**
  1. **`factories.py`** — helper que gera PDFs mínimos em memória para os testes (texto conhecido, N páginas, e um caso sem camada de texto). *Por quê em código:* commitar PDF binário como fixture polui o repositório e esconde o que está sendo testado.
  2. **`adapters/pdf.py: extract_pages(data: bytes) -> list[PageText]`** — abre com `pypdf`, itera páginas, extrai texto, preserva o número base 1. Docstring explicando que é bloqueante e deve rodar em thread.
  3. **Validações que exigem parse**, cada uma levantando exceção de domínio distinta com mensagem pt-BR: páginas acima de `MAX_PDF_PAGES`; soma de caracteres acima de `MAX_EXTRACTED_CHARS`; zero caractere extraível ("PDF sem texto extraível; OCR não é suportado").
  4. **`core/chunking.py: chunk_pages(pages, size, overlap) -> list[Chunk]`** — itera **página a página**; a janela **reseta em cada página**. Corte em fronteira de parágrafo (`\n\n`), depois de sentença (`. `, `! `, `? `), depois de espaço; nunca no meio de palavra. `chunk_index` é sequencial no documento inteiro; `page_number` é o da página iterada.
  5. Normalizar espaços em branco excessivos preservando a fronteira de parágrafo. *Por quê:* PDFs produzem quebras espúrias que estragam tanto o corte quanto o texto que vai para o chip de citação.
  6. Docstrings em todas as funções públicas, dizendo o que fazem e **por que a regra existe** (a de `chunk_pages` deve dizer explicitamente que não cruzar página é o que torna a citação exata).
- **Testes:** página correta e nenhum chunk multi-página (AC-6); determinismo entre execuções (AC-6); corte não parte palavra e overlap mínimo respeitado (AC-7); página menor que a janela vira um chunk; as três violações levantam a exceção certa (AC-4, AC-5).
- **Escopo travado / violações BLOQUEANTES:** `core/chunking.py` não pode importar `fastapi`, `asyncpg`, `google.genai` nem `structlog` — `make arch` reprova; não usar splitter de terceiros; não fazer OCR; não commitar PDF binário; **não deixar um chunk cruzar fronteira de página**.
- **Critério de conclusão (gate):** testes verdes sem rede e sem banco; cobertura de `core/chunking.py` ≥ 90% (AC-29); `make check` zero.

### Fase A.3 — Adapter Gemini de embeddings *(tamanho M; ≈2h)*

- **id:** `A.3`
- **slug:** `gemini-embeddings`
- **Objetivo:** converter textos em vetores respeitando o contrato de §4.2 e as restrições do free tier, sem vazar segredo.
- **Por que esta fase existe:** é o único ponto do sistema que fala com a rede, e o único onde um erro silencioso corrompe tudo a jusante sem quebrar teste nenhum. Por isso ela começa com uma verificação contra a API real, antes de qualquer código de produção.
- **Depende de:** `A.1`
- **Contexto que o agente precisa:** o contrato de §4.2 é decisão fechada — modelo, dimensão, `task_type`, normalização e tamanho de lote não estão em aberto. A normalização L2 **é obrigatória** porque o modelo só entrega vetor normalizado quando a dimensão é 3072, e estamos pedindo 768; sem normalizar, a distância de cosseno da `FEAT-0002` mente. `embed_query` é implementado **aqui** e consumido lá — não deixe como stub, e teste-o, senão a fase de eval da `FEAT-0002` fica bloqueada por um método que ninguém validou.
- **Arquivos novos:** `backend/app/adapters/gemini.py`, `backend/scripts/check_embeddings.py`, `backend/tests/test_gemini_adapter.py`. **Arquivos alterados:** `backend/eval/README.md` (criar com o registro da verificação).
- **Passos:**
  1. **Antes de qualquer código de produção:** escrever e rodar `scripts/check_embeddings.py` contra a API real, conforme §4.2. Se o modelo devolver um vetor agregado em vez de N, embrulhar cada texto num objeto `Content` e repetir até a asserção passar. **Registrar o resultado em `backend/eval/README.md`** — esse registro é o que impede a dúvida de voltar.
  2. **Protocolo `EmbeddingClient`** (`typing.Protocol`) com `embed_documents(texts: list[str]) -> list[list[float]]` e `embed_query(text: str) -> list[float]`. *Por quê protocolo e não classe base:* é o que permite o fake dos testes existir sem herança e sem importar o SDK.
  3. Implementação com `google-genai`, em lotes de `EMBEDDING_BATCH_SIZE`, passando `task_type` e `output_dimensionality` de §4.2. Validar a presença de `GEMINI_API_KEY` aqui, levantando erro de domínio claro se vazia.
  4. **Normalizar L2** todo vetor antes de entregar, com uma função pura testável.
  5. Backoff exponencial com jitter para transitório e `429`, teto de tentativas configurável, emitindo `embedding.retry` a cada tentativa. `400` de payload é permanente: não repete, e levanta erro próprio.
  6. **Sanitizar** toda exceção propagada: nenhum fragmento de chave pode sobreviver na mensagem. Implementar como função dedicada e testá-la isoladamente.
  7. Emitir `embedding.batch` (debug) por lote, com `batch_index`, `batch_size` e `duration_ms`.
- **Testes:** `ceil(N/B)` requisições (AC-8); `429` aciona backoff e conclui, `400` não repete (AC-9); norma L2 = 1,0 e `task_type` distintos entre os dois métodos (AC-10); chave nunca aparece na exceção nem no log (AC-13, AC-19). Todos com cliente falso — **nenhum teste chama a API real**.
- **Escopo travado / violações BLOQUEANTES:** não logar a chave nem fragmento dela; não fazer uma requisição por chunk; não usar `except Exception` sem reclassificar; não deixar retry infinito; **não implementar pool de chaves** (cortado: os limites do free tier são por projeto, não por chave).
- **Critério de conclusão (gate):** `check_embeddings.py` passou contra a API real e está registrado em `backend/eval/README.md`; testes verdes sem rede; `make check` zero.

### Fase A.4 — Pipeline de ingestão e rotas *(tamanho L; ≈3h)*

- **id:** `A.4`
- **slug:** `ingestion-pipeline`
- **Objetivo:** amarrar upload, extração, chunking, embeddings e persistência numa máquina de estados consultável e bem logada.
- **Por que esta fase existe:** é onde o requisito 1 do desafio passa a existir de fato, e onde "tratamento do upload e de erros" — nomeado no eixo de Engenharia — é avaliado. A separação entre o que é validado na requisição e o que é validado em background é a decisão central: tudo que exige parse do PDF é caro demais para a requisição.
- **Depende de:** `A.2`, `A.3`
- **Contexto que o agente precisa:** `MAX_UPLOAD_MB` não pode ser aplicado depois de `await file.read()` — nesse ponto o arquivo já está inteiro na memória. Por isso a checagem é de `Content-Length` **antes** de ler, mais leitura em pedaços com corte rígido. O `BackgroundTasks` do Starlette roda dentro do `AsyncExitStack` do request e **não** é morto em tarefas de minutos (verificado na revisão), mas passe `bytes` e não o `UploadFile`, para não depender desse detalhe. O `request_id` do middleware precisa ser propagado para dentro da task — capture-o antes de agendar.
- **Arquivos novos:** `backend/app/adapters/repository.py`, `backend/app/ingestion.py`, `backend/app/api/documents.py`. **Arquivos alterados:** `backend/app/main.py`, `backend/app/api/schemas.py`.
- **Passos:**
  1. **Protocolo `DocumentRepository`** e implementação com SQL parametrizado: `create`, `get`, `find_by_hash(session_id, content_hash)`, `set_status`, `update_progress`, `insert_chunks` (em lote, com `executemany` ou `copy`), `sweep_orphans`. *Por quê protocolo:* é o que permite o `FakeRepository` da `A.5` tornar a suíte offline.
  2. **`POST /api/documents`**: checar `Content-Length` contra `MAX_UPLOAD_MB` → `413`; ler em pedaços com corte rígido; conferir assinatura `%PDF` → `422`; calcular SHA-256; se `find_by_hash` acha, emitir `document.duplicate` e devolver o documento existente; senão persistir `pending`, emitir `document.received`, agendar `BackgroundTasks` com `bytes` e o `request_id`, responder `202`.
  3. **Pipeline em `ingestion.py`**: adquirir o semáforo global (NFR-8) → `set_status(processing)` → `await asyncio.to_thread(extract_pages, data)` → validações de FR-3 → `chunk_pages` → embeddings em lotes, chamando `update_progress` após cada lote → `insert_chunks` → `set_status(ready)`. Emitir os eventos de §4.4 em cada etapa, com `duration_ms`.
  4. **Uma extração só:** o resultado de `extract_pages` é reusado; não parsear o PDF duas vezes.
  5. **`try/except/finally`**: toda exceção de domínio vira `failed` com a mensagem correspondente e evento `document.failed`; exceção inesperada vira `failed` com `erro_interno` e o traceback **no log**, nunca na mensagem ao usuário. O `finally` garante que nenhum caminho deixa o documento em `processing`.
  6. **`GET /api/documents/{id}`** devolvendo o payload de §4.5; `404` com `code: "nao_encontrado"`.
  7. Gravar `session_id` do header `X-Session-Id` (sem usá-lo para autorização).
- **Testes:** upload responde rápido em `pending` (AC-1); limites da requisição recusados no envelope certo (AC-2, AC-3); violações de parse terminam `failed` (AC-4, AC-5); progresso monotônico (AC-12); falha permanente vira `failed` sem vazar chave (AC-13); reenvio idêntico não reprocessa (AC-15); dois uploads simultâneos serializam (AC-28); os eventos de log aparecem com o mesmo `request_id` (AC-18).
- **Escopo travado / violações BLOQUEANTES:** nenhuma chamada ao Gemini fora do adapter da `A.3`; nenhum SQL concatenado; **não deixar documento preso em `processing`**; não parsear o PDF duas vezes; não bloquear o event loop com `pypdf`; não implementar retrieval nem chat; não gravar o conteúdo do PDF em log.
- **Critério de conclusão (gate):** upload real do `Exemplo-YAITEC.pdf` chega a `ready` com chunks embedados; o índice HNSW é o de cosseno (AC-11); um `docker compose logs backend | grep <request_id>` mostra a ingestão inteira; `make check` zero.

### Fase A.5 — Suíte de testes da ingestão *(tamanho M; ≈2h)*

- **id:** `A.5`
- **slug:** `ingestion-tests`
- **Objetivo:** provar o fluxo do backend de forma determinística e **offline**, com um conjunto pequeno e explícito de testes contra banco real.
- **Por que esta fase existe:** o gate de toda fase é `make check`, e `make check` roda no host de quem clona. Uma suíte que exige Postgres e chave de API não é gate — é obstáculo. O `FakeRepository` é o que torna a suíte executável em qualquer máquina, e é também o que prova que a arquitetura em camadas não é decorativa.
- **Depende de:** `A.4`
- **Contexto que o agente precisa:** `make test` roda `pytest` no host com `addopts = "-m 'not db'"`, então tudo que exige banco precisa do marker `db` e vive em `make test-db`. O `BackgroundTasks` do Starlette termina **antes** de o `TestClient` retornar o POST, então a transição `pending → processing → ready` é inobservável pela rota — teste a função de pipeline diretamente com um fake que registra as chamadas de progresso.
- **Arquivos novos:** `backend/tests/{conftest,fakes,test_ingestion_api,test_ingestion_db,test_logging}.py`. **Arquivos alterados:** `backend/pyproject.toml` (marker `db`, `addopts`, config de cobertura).
- **Passos:**
  1. **`fakes.py`** — `FakeEmbeddingClient` (vetor determinístico derivado de hash, já normalizado) e `FakeRepository` (dicionário em memória) implementando os protocolos de `A.3` e `A.4`.
  2. **`conftest.py`** — fixtures que injetam os fakes por override de dependência do FastAPI, e uma que captura a saída do structlog para inspeção.
  3. **`test_ingestion_api.py`** — fluxo `upload → estado → ready → chunks registrados`; recusas por limite; falha de provedor; reenvio duplicado; dois uploads concorrentes.
  4. **`test_logging.py`** — verifica que a ingestão emite os eventos nomeados de §4.4 com o mesmo `request_id` (AC-18) e que, com uma `GEMINI_API_KEY` definida no ambiente do teste, a string da chave **não aparece** em nenhum log capturado, em nenhum caminho de erro (AC-19).
  5. **`test_ingestion_db.py`** marcado `@pytest.mark.db` — cobre AC-11 (colunas reais e índice HNSW de cosseno) contra o Postgres do compose.
  6. **Cobertura:** configurar `--cov=app/core --cov-fail-under=90` no `addopts`, para NFR-10 ser gate e não intenção.
- **Testes:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-12, AC-13, AC-15, AC-17, AC-18, AC-19, AC-28 offline; AC-11 sob o marker `db`; AC-29 pelo gate de cobertura.
- **Escopo travado / violações BLOQUEANTES:** nenhum teste do `make test` pode exigir rede, banco ou `GEMINI_API_KEY`; nenhum `skip` ou `retry` para mascarar flakiness; não testar implementação privada quando a rota cobre o comportamento; não baixar o `--cov-fail-under` para fazer passar.
- **Critério de conclusão (gate):** `make test` verde **sem `GEMINI_API_KEY` e sem o compose no ar**, com cobertura de `core/` ≥ 90% (AC-25, AC-29); `make test-db` verde com o compose no ar.

### Fase A.6 — Gates de arquitetura e segurança *(tamanho S; ≈1h)*

- **id:** `A.6`
- **slug:** `quality-gates`
- **Objetivo:** transformar os princípios invioláveis em comandos que falham, e provar as propriedades de segurança com teste, não com afirmação.
- **Por que esta fase existe:** um princípio que só existe em documento é uma intenção. `make arch` falhando quando alguém importa `asyncpg` dentro de `core/` é uma garantia. Essa diferença é exatamente o que o eixo de Engenharia avalia, e é barata de obter.
- **Depende de:** `A.4`
- **Contexto que o agente precisa:** `import-linter 2.13`, `bandit 1.9.4` e `structlog 26.1.0` já estão no `pyproject.toml` e verificados. O `Makefile` já tem os alvos `arch` e `security`. O arquivo `backend/.importlinter` foi criado na `A.1` com os três contratos de §4.8 — esta fase os **endurece e prova**, escrevendo um teste que confirma que o gate realmente reprova uma violação.
- **Arquivos novos:** `backend/tests/{test_architecture,test_security}.py`. **Arquivos alterados:** `backend/.importlinter`, `backend/pyproject.toml` (config do bandit, se necessário).
- **Passos:**
  1. Revisar os três contratos do `.importlinter` contra a estrutura real já implementada, incluindo `structlog` na lista de proibições de `app.core`. *Por quê proibir structlog no core:* logging é efeito colateral; um núcleo que loga não é puro e passa a exigir configuração para ser testado.
  2. **`test_architecture.py`** — teste que executa `lint-imports` como subprocesso e afirma saída zero; e um segundo que cria um módulo temporário violando o contrato e afirma que o comando **falha** (AC-24). *Por quê o segundo:* um gate que nunca reprovou nada pode estar mal configurado e ninguém saberia.
  3. **`test_security.py`** — três testes de comportamento: (a) a chave não aparece em log em nenhum caminho de erro (reforça AC-19 fora do módulo de logging); (b) `find_by_hash` e `get` resistem a input com aspas, `;` e `--`, provando que o SQL é parametrizado; (c) upload com `filename` malicioso (`../../etc/passwd`) é armazenado como nome, sem nunca virar caminho de sistema de arquivos.
  4. Rodar `make security` e resolver os achados de severidade alta. `bandit` costuma sinalizar `assert` em testes — restringir o escopo a `app`, como já está no Makefile.
  5. Documentar em `backend/README.md` (ou seção do README raiz, decidido na `FEAT-0002 B.5`) o que cada gate garante.
- **Testes:** `make arch` passa e reprova violação injetada (AC-24); os três testes de segurança passam (AC-19, AC-30); `make security` sem achado alto (AC-30).
- **Escopo travado / violações BLOQUEANTES:** não afrouxar contrato para fazer o código passar — se o contrato reprova, o código muda; não adicionar `# nosec` sem comentário justificando; não desabilitar regra do bandit globalmente.
- **Critério de conclusão (gate):** `make check` (agora com `arch`) e `make security` zero; o teste de violação injetada prova que o gate morde.

### Track B — Frontend

### Fase B.1 — Design system e casca visual *(tamanho M; ≈2,5h)*

- **id:** `B.1`
- **slug:** `design-system`
- **Objetivo:** estabelecer a base visual — tokens, tipografia, espaçamento, tema claro/escuro, componentes primitivos e o layout da aplicação — antes de qualquer tela existir.
- **Por que esta fase existe:** o eixo Produto/UX é um terço da avaliação, e o plano anterior não tinha uma linha sobre design. Tailwind sem sistema produz tela cinza funcional que passa em todos os critérios de aceite e não parece produto. Fazer isto **primeiro** também evita o retrabalho de estilizar telas duas vezes.
- **Depende de:** nenhuma
- **Contexto que o agente precisa:** `frontend/` já tem `package.json` (React 19, Vite 6, Tailwind 4, TypeScript 5.7, eslint 9), `tsconfig.json` com `strict`, `vite.config.ts` com os plugins `react()` e `tailwindcss()`, `nginx.conf` e `Dockerfile` multi-stage — todos funcionando. **Verificado:** shadcn/ui suporta Tailwind v4 e React 19 e usa exatamente esses plugins; a inicialização exige o alias `@` em `tsconfig` e em `vite.config.ts`. O CLI **copia** os componentes para `src/components/ui/` — eles passam a ser código do projeto, versionado e editável, não dependência opaca. Rodar o CLI vai alterar `package-lock.json`; isso é esperado, e o lock deve ser recommitado.
- **Arquivos novos:** `frontend/index.html`, `frontend/components.json`, `frontend/src/{main.tsx,App.tsx,index.css}`, `frontend/src/lib/utils.ts`, `frontend/src/components/ui/*`, `frontend/src/components/AppShell.tsx`, `frontend/eslint.config.js`. **Arquivos alterados:** `frontend/{tsconfig.json,vite.config.ts,package.json,package-lock.json}`.
- **Passos:**
  1. Criar `index.html` e `main.tsx` montando o `App`; `index.css` com `@import "tailwindcss";`.
  2. Configurar o alias `@` em `tsconfig.json` (`baseUrl` + `paths`) e em `vite.config.ts` (`resolve.alias` com `path.resolve`). *Por quê:* é pré-requisito do CLI do shadcn e melhora a legibilidade dos imports.
  3. Inicializar o shadcn (`npx shadcn@latest init`), escolhendo modo TypeScript e o estilo padrão. Isso cria `components.json` e `src/lib/utils.ts`.
  4. Adicionar os componentes de §4.7: `button`, `card`, `progress`, `scroll-area`, `separator`, `skeleton`, `sonner`, `tooltip`, `badge`, `dialog`.
  5. **Definir os tokens do projeto** em `index.css`, sobre as variáveis OKLCH que o shadcn gera: paleta (uma cor de marca, neutros, e as semânticas de sucesso/aviso/erro), escala tipográfica (no máximo quatro tamanhos), raio de borda e escala de espaçamento. Definir tema claro **e** escuro, ambos com contraste AA.
  6. **`AppShell.tsx`** — cabeçalho com o nome do produto e alternador de tema; área de conteúdo com largura máxima legível (~72ch para texto, mais larga para o chat); rodapé discreto. Layout em grid, utilizável a 375 px.
  7. `eslint.config.js` (flat config) com `typescript-eslint` e `react-hooks`.
  8. Documentar em comentário no `index.css` o que cada token significa e quando usar — o owner vai revisar e ajustar.
- **Testes:** `npx tsc --noEmit` e `npm run lint` zero; a página é servida pelo container em `localhost:5173`; alternância de tema funciona; navegação por `Tab` alcança todos os controles (AC-23).
- **Escopo travado / violações BLOQUEANTES:** não instalar biblioteca de estado global; não instalar UI kit adicional além do shadcn; **não usar cor fora dos tokens**; não afrouxar `strict` do TypeScript; não criar telas de upload ou chat nesta fase — só a casca.
- **Critério de conclusão (gate):** container serve a casca nos dois temas, responsiva a 375 px, com foco visível e navegação por teclado; lint e typecheck zero.

### Fase B.2 — Camada de dados e sistema de avisos *(tamanho M; ≈2h)*

- **id:** `B.2`
- **slug:** `app-shell`
- **Objetivo:** cliente HTTP alinhado ao envelope de erro, identidade de sessão, limites vindos da API, e o componente único que dá avisos ao usuário.
- **Por que esta fase existe:** o owner nomeou "os avisos ao usuário" como uma das coisas que precisam funcionar bem. Espalhar mensagens por componentes garante inconsistência; centralizar num mapa `code → mensagem + ação` garante que toda falha do sistema tenha uma frase pensada, e que a `FEAT-0002` reuse a mesma.
- **Depende de:** `B.1`
- **Contexto que o agente precisa:** o envelope de erro está em §4.3 e é **fonte única** — o cliente mapeia por `code`, nunca por status, porque a `FEAT-0002` emitirá os mesmos códigos por SSE, onde não há status HTTP. O `api.ts` precisa de fallback para resposta não-JSON: um proxy mal configurado pode responder HTML, e chamar `response.json()` em cima disso quebra de forma opaca. `GET /api/config` existe desde a `A.1`.
- **Arquivos novos:** `frontend/src/lib/{api,session,types,errors,config}.ts`, `frontend/src/components/Notices.tsx`, `frontend/src/hooks/useNotices.ts`. **Arquivos alterados:** `frontend/src/App.tsx`.
- **Passos:**
  1. **`session.ts`** — UUID em `localStorage`, gerado com `crypto.randomUUID()` na primeira visita.
  2. **`types.ts`** — tipos espelhando §4.5, escritos **a partir da spec** (não de `schemas.py`, que pode ainda não existir quando esta fase roda).
  3. **`api.ts`** — wrapper de `fetch` com base `/api`, header `X-Session-Id`, timeout, e normalização de erro que lê `{code, message}` **com fallback** quando a resposta não é JSON (usa `erro_interno` e a mensagem genérica).
  4. **`errors.ts`** — mapa `code → {título, mensagem pt-BR, ação sugerida, severidade}` cobrindo os cinco códigos de §4.3, mais `rede_indisponivel` para falha de fetch. Exportar uma função `describeError(code)`.
  5. **`config.ts`** — busca `GET /api/config` no boot, expõe os limites, e trata a falha dessa chamada com um estado degradado explícito (não travar o app).
  6. **`Notices.tsx` + `useNotices.ts`** — camada única de aviso sobre o `sonner` do shadcn, com três níveis (informação, sucesso, erro) e API `notify.error(code)` / `notify.success(msg)`. Aviso de erro sempre traz ação.
  7. Ligar tudo no `App.tsx`: provider de avisos, carregamento de config, estado inicial.
- **Testes:** `describeError` cobre todos os códigos de §4.3; resposta não-JSON não quebra o cliente; `tsc --noEmit` e `npm run lint` zero.
- **Escopo travado / violações BLOQUEANTES:** **não mapear erro por status HTTP** — só por `code`; não duplicar os limites do servidor em constantes; não usar `alert()`; não exibir stack trace, corpo bruto de erro ou nome de exceção; textos em pt-BR e identificadores em inglês.
- **Critério de conclusão (gate):** um erro forçado do backend aparece como aviso com título, mensagem e ação em pt-BR; lint e typecheck zero.

### Fase B.3 — Tela de upload *(tamanho M; ≈2h)*

- **id:** `B.3`
- **slug:** `upload-view`
- **Objetivo:** enviar um PDF com validação local coerente com o servidor e feedback de envio.
- **Por que esta fase existe:** é a primeira tela que o avaliador vê. A validação local existe para dar resposta imediata, não para substituir o servidor — e por isso lê os limites da API, em vez de duplicá-los.
- **Depende de:** `B.2`, `A.4`
- **Contexto que o agente precisa:** o `fetch` **não reporta progresso de upload** — cumprir isso exigiria `XMLHttpRequest`, e para arquivos de dezenas de MB em localhost o envio dura milissegundos. Use indicador indeterminado; a barra que importa é a de **processamento**, na `B.4`. O backend responde `202` com `{id, status}`; guarde o `id` em `localStorage` para sobreviver a um recarregamento.
- **Arquivos novos:** `frontend/src/components/UploadDropzone.tsx`, `frontend/src/hooks/useUpload.ts`. **Arquivos alterados:** `frontend/src/App.tsx`.
- **Passos:**
  1. Dropzone sobre `Card` do design system, com clique e arrastar-soltar, aceitando só `application/pdf`, com estado visual de "arrastando sobre".
  2. Validar extensão e tamanho contra os limites de `config.ts`, disparando `notify.error` com a mensagem do `errors.ts` quando violado.
  3. **`useUpload`** enviando `FormData` no campo `file`, com estado `idle | enviando | erro`, e indicador indeterminado durante o envio.
  4. Exibir nome e tamanho do arquivo escolhido, com opção de trocar antes de enviar.
  5. Ao receber `202`, persistir o `id` em `localStorage` e passar o controle para o acompanhamento.
  6. Estado vazio com instrução clara do que fazer, e área de arrastar acessível por teclado (input de arquivo real, rotulado).
- **Testes:** arquivo acima do limite é bloqueado antes da requisição com aviso em pt-BR (AC-20); PDF válido mostra nome, tamanho e indicador (AC-21); a área é operável por teclado (AC-23).
- **Escopo travado / violações BLOQUEANTES:** validação no cliente **não** substitui a do servidor; não aceitar outros formatos; **não prometer barra de progresso de upload**; não usar cor fora dos tokens.
- **Critério de conclusão (gate):** upload de ponta a ponta **através do `docker compose`**, não do dev server; lint e typecheck zero.

### Fase B.4 — Acompanhamento do processamento *(tamanho M; ≈2h)*

- **id:** `B.4`
- **slug:** `processing-status`
- **Objetivo:** mostrar honestamente o que está acontecendo durante o processamento, e sobreviver a um recarregamento.
- **Por que esta fase existe:** o enunciado pede explicitamente "mostre ao usuário que está processando". Como a ingestão leva dezenas de segundos por causa da quota, esta tela é onde o app parece vivo ou parece travado — e a diferença é mostrar progresso derivado de dado real, não uma animação genérica.
- **Depende de:** `B.3`
- **Contexto que o agente precisa:** `GET /api/documents/{id}` devolve `chunks_processed` e `chunks_total`; `chunks_total` só é conhecido depois do chunking, então há uma janela inicial em que o progresso é legitimamente indeterminado — mostre isso, não invente número. O documento pode terminar em `failed` com `error_message` vinda do backend, já em pt-BR: exiba a mensagem do servidor, não uma genérica.
- **Arquivos novos:** `frontend/src/components/ProcessingStatus.tsx`, `frontend/src/hooks/useDocumentStatus.ts`. **Arquivos alterados:** `frontend/src/App.tsx`, `frontend/src/components/UploadDropzone.tsx`.
- **Passos:**
  1. **`useDocumentStatus`** com polling de intervalo mínimo 1 s, parando em `ready` ou `failed`, limpando o timer ao desmontar, e tratando erro de rede sem derrubar o estado.
  2. Renderizar os quatro estados com rótulo em pt-BR, usando `Progress` e `Skeleton` do design system; barra determinada quando `chunks_total` é conhecido, indeterminada antes disso.
  3. **Ao montar, se houver `documentId` em `localStorage`, retomar o acompanhamento** — recarregar a página não perde o documento.
  4. Em `failed`, exibir a `error_message` do backend com ação de enviar outro arquivo.
  5. Em `ready`, sinalizar que o documento está pronto para conversa — este é o gancho que a `FEAT-0002 B.1` consome.
  6. Anunciar a mudança de estado para leitores de tela (região `aria-live` polida).
- **Testes:** transição visível sem recarregar (AC-22); progresso monotônico na barra (AC-12); documento `failed` mostra a mensagem do backend (AC-5); recarregar retoma o acompanhamento; `aria-live` presente (AC-23).
- **Escopo travado / violações BLOQUEANTES:** não fazer polling mais agressivo que 1 s; não deixar timer órfão; **não inventar progresso** que o backend não informou; não exibir stack trace nem corpo bruto.
- **Critério de conclusão (gate):** ciclo `upload → processando → pronto` observável no compose e sobrevivendo a um `F5`; lint e typecheck zero.

## 6. Riscos

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| 1 | O modelo devolver vetor agregado em vez de N vetores | Média | Alto | Verificação contra a API real no primeiro passo da `A.3`, antes de qualquer código de pipeline |
| 2 | Quota estourar durante a avaliação | Média | Médio | Limites por env, lote de 16, backoff, dedup por hash, semáforo; `429` vira aviso claro |
| 3 | `init.sql` não reaplicar após mudança de schema | Alta | Médio | `A.1` fixa o schema inteiro de uma vez; `make stop` preserva e `make down` destrói, documentado |
| 4 | `BackgroundTasks` perder o processamento num restart | Média | Baixo | Varredura de órfãos no lifespan (FR-13) — o usuário vê o que houve em vez de barra eterna |
| 5 | CLI do shadcn alterar arquivos de config de forma inesperada | Média | Baixo | `B.1` é a primeira fase do track e roda antes de qualquer tela; `package-lock.json` recommitado |
| 6 | Design ficar genérico apesar do design system | Média | Médio | `B.1` exige tokens próprios, não os defaults; o owner revisa e ajusta ao fim |
| 7 | Tracks divergirem no contrato de API | Baixa | Médio | §4.5 é fonte única, escrita antes das fases; `types.ts` derivado da spec |
| 8 | Regressão em um dos seis defeitos de §4.1 | Baixa | Alto | Escopo travado da `A.1`; gate exige `up --build` a frio duas vezes e `curl` através do nginx |

## 7. Rollout

Sem produção e sem flag: a entrega é o repositório privado com `docker compose up`.

`A.1` primeiro — destrava o compose e fixa os contratos. Depois `A.2` e `A.3` em paralelo. `A.4` amarra; `A.5` e `A.6` fecham a qualidade.

No Track B, `B.1` pode começar imediatamente, em paralelo com `A.1` — não depende de backend. `B.3` é o primeiro ponto de acoplamento (depende de `A.4`).

Ordem recomendada com duas frentes: `A.1` + `B.1` juntas; depois `A.2`/`A.3` + `B.2`; depois `A.4` + `B.3`; depois `A.5`/`A.6` + `B.4`.

Rollback é `git revert` da fase. Mudança de schema exige `make down` antes do próximo `up`.

## 8. Open Questions

- **OQ-1 — Estratégia de chunking.** **RESOLVIDO (2026-08-17):** por página, sem cruzar fronteira, janela de 500 caracteres e overlap de 100 dentro da página. *Justificativa:* torna a citação exata por construção, e eleva o PDF de exemplo de ~4 para ~10 chunks, fazendo o `RETRIEVAL_TOP_K=5` da `FEAT-0002` selecionar de fato. *Rejeitado:* janela deslizante contínua com a página do início do chunk (citação errada ao cruzar fronteira); chunk por página inteira (grosso demais para um chip de citação).
- **OQ-5 — Processamento síncrono ou assíncrono.** **RESOLVIDO (2026-08-17):** `BackgroundTasks` com máquina de estados por polling. *Justificativa:* 20 páginas levam ~40 s só de embedding, além de qualquer timeout; e o enunciado pede o feedback de processamento. *Verificado na revisão:* `BackgroundTasks` não é morto em tarefas dessa duração.
- **OQ-7 — Limites do PDF.** **RESOLVIDO (2026-08-17):** `MAX_UPLOAD_MB=25` (upload e memória); `MAX_PDF_PAGES=20` e `MAX_EXTRACTED_CHARS=60000` (quota). *Justificativa:* megabyte é proxy ruim de custo de embedding. *Rejeitado:* limite único em MB.
- **OQ-8 — Pool de chaves Gemini.** **RESOLVIDO (2026-08-17): cortado.** *Justificativa:* os limites do free tier são por projeto, não por chave — o recurso não faria nada. *Rejeitado:* manter como opcional.
- **OQ-9 — Modelo e dimensão do embedding.** **RESOLVIDO (2026-08-17):** `gemini-embedding-001`, 768 dimensões, normalização L2, `task_type` assimétrico, índice `vector_cosine_ops`. *Justificativa:* o default de 3072 faria o `CREATE INDEX` abortar dentro do initdb (o pgvector não indexa acima de 2000), derrubando o compose a frio. *Rejeitado:* decidir na fase do adapter. *Consequência aceita:* `EMBEDDING_DIM` deixa de ser configurável na prática, e o lifespan valida a coerência.
- **OQ-15 — Abordagem de interface.** **RESOLVIDO (2026-08-17):** design system sobre shadcn/ui, com tokens próprios, tema claro e escuro. *Justificativa:* decisão do owner, que definiu boa UI/UX como indispensável e pediu para partir de um template maduro em vez de CSS artesanal; o eixo Produto/UX é um terço da nota, e componentes com acessibilidade resolvida economizam horas. *Rejeitado:* CSS artesanal sobre Tailwind puro (produz tela genérica no prazo disponível) e template de chatbot pronto de terceiros (traria opiniões de arquitetura e dependências que não controlamos).
- **OQ-16 — Ferramenta de logging.** **RESOLVIDO (2026-08-17):** `structlog` com renderer JSON. *Justificativa:* o binding de contexto é o que permite rastrear uma ingestão inteira por `request_id` sem repetir campos; verificado que instala e roda (26.1.0). *Rejeitado:* `logging` da stdlib com formatter JSON — funcionaria, mas exigiria passar contexto à mão em cada chamada.

## 9. Definition of Done (gate por etapa)

**Gate por fase** — todas concluídas; o veredito de cada uma está em
`artefatos/FASE-<id>-<slug>-AVALIACAO.md`, com o par (`fase`, `tentativa`)
fechado:

- [✓] `A.1 foundation` — compose sobe a frio duas vezes; `/api/health` `200` através do nginx com `X-Request-Id`; envelope de erro aplicado; `make arch` passa. *(APROVADO 9,5 · tentativa 2)*
- [✓] `A.2 pdf-chunking` — chunking por página, determinístico, offline, cobertura ≥ 90%. *(APROVADO 9,8 · tentativa 2)*
- [✓] `A.3 gemini-embeddings` — verificação contra a API real registrada; lote, backoff, `task_type` e L2 testados com fake. *(APROVADO 9,8 · tentativa 2)*
- [✓] `A.4 ingestion-pipeline` — `Exemplo-YAITEC.pdf` chega a `ready`; ingestão rastreável por `request_id` no log. *(APROVADO 9,8 · tentativa 2)*
- [✓] `A.5 ingestion-tests` — `make test` verde sem chave e sem banco, cobertura de `core/` ≥ 90%; `make test-db` verde. *(APROVADO 9,8 · tentativa 1)*
- [✓] `A.6 quality-gates` — `make arch` reprova violação injetada; `make security` sem achado alto. *(APROVADO 9,7 · tentativa 1)*
- [✓] `B.1 design-system` — casca nos dois temas, responsiva a 375 px, navegável por teclado. *(APROVADO · tentativa 1)*
- [✓] `B.2 app-shell` — erro do backend vira aviso com título, mensagem e ação em pt-BR. *(APROVADO · tentativa 2)*
- [✓] `B.3 upload-view` — upload de ponta a ponta pelo compose. *(APROVADO · tentativa 2)*
- [✓] `B.4 processing-status` — transição visível, sobrevivendo a `F5`, com `aria-live`. *(APROVADO · tentativa 2)*

**Itens globais transversais:**

- [✓] Cada FR e cada NFR tem ao menos um AC verificado.
- [✓] `make check` (lint + typecheck + arch + test) retorna zero, rodando offline — 135 testes de backend e 40 de frontend.
- [✓] `make security` retorna zero achados de severidade alta.
- [✓] Cobertura de `backend/app/core/` ≥ 90% — 98,98%, travada por `--cov-fail-under=90`.
- [✓] Toda função pública de `core/` e `adapters/` tem docstring dizendo o que faz e por quê — verificado por varredura de AST na reavaliação da `A.4`.
- [✓] Nenhum módulo de `backend/app/core/` importa `fastapi`, `asyncpg`, `google.genai` ou `structlog` — contrato `pure-core`, provado por violação injetada.
- [✓] Nenhuma dependência de framework de RAG — contrato `no-rag-framework`, com as distribuições `langchain_*` e `llama_index_*` nomeadas uma a uma.
- [✓] Nenhuma chave, `DATABASE_URL` ou conteúdo de PDF em log, resposta ou arquivo versionado — verificado por teste, e confirmado na árvore do HEAD (`git grep` do fragmento = zero). *Ressalva do owner, fora do código: um fragmento de 9 caracteres da chave real permanece no histórico. Ele entrou em `d6f42d3`, saiu em `34cb479`, **voltou** em `3430e91` e saiu de novo em `bff6e9f` — são dois intervalos a limpar, não um, se a opção for reescrever a história. A remediação barata e suficiente é rotacionar a chave.*
- [✓] Todo SQL é parametrizado — verificado por teste contra o Postgres real, com payload destrutivo.
- [ ] Identificadores em inglês; textos de UI e mensagens de erro em pt-BR. *Metade cumprida: os textos estão todos em pt-BR e o backend não tem um identificador em português. No frontend sobra `semResposta` (`src/lib/api.ts:57`, usado em `:76` e `:89`) mais 11 identificadores em arquivos de teste (`documento`, `campoDeArquivo`, `montar`, `titulo`, `opcoes`, `avancar`, `CODIGOS_DA_SPEC`…). Os **nomes dos casos de teste** em pt-BR não contam e devem ficar — são documentação de comportamento. Registrado como sugestão nas avaliações da `B.2` (§5.1) e da `B.3` (§6.1).*
- [✓] Toda cor, tamanho de texto e espaçamento vem dos tokens do design system.
- [✓] `docker compose up --build` de clone limpo sobe tudo e a tela responde em `localhost:5173` — evidência do executor (dois boots a frio com os três serviços reais, §9 do relatório da `A.1`) e do avaliador do Track B; o avaliador do Track A não a reproduziu, porque exige a `GEMINI_API_KEY`.
- [✓] `.env.example` documenta toda variável que `config.py` lê — sem sobra e sem falta.
- [✓] Nenhum dos seis defeitos de infraestrutura de §4.1 voltou.

**Pendências que sobrevivem ao fechamento da spec** (não bloqueiam as fases;
estão registradas nas avaliações):

- Rotacionar a `GEMINI_API_KEY` — ação do owner, ver a avaliação da `A.1`. O
  fragmento está em dois intervalos do histórico (`d6f42d3..34cb479` e
  `3430e91..bff6e9f`); a árvore do HEAD está limpa.
- Renomear `semResposta` para `noResponse` em `frontend/src/lib/api.ts` e passar
  os helpers dos testes do frontend para inglês — é o único item global desta
  seção que ficou aberto, e é o trabalho de um `sed` revisado à mão.
- Dois reenvios simultâneos de um documento `failed` duplicam chunks no
  Postgres, e o dublê da suíte não enxerga porque `insert_chunks` atribui onde o
  banco acumula — sugestão S-1 da avaliação da `A.4`.
- Falta o teste de nível de pipeline provando que um transitório de transporte
  não vira `erro_interno` para o usuário — sugestão da avaliação da `A.3`.
