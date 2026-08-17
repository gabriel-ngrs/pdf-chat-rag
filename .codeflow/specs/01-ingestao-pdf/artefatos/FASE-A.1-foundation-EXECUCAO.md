---
spec: 01-ingestao-pdf
fase: A.1
slug_fase: foundation
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: 26ba58610514ac27c86595b01ee657795d382c92
sha_final: c7e05f406f69253427835628b0639aad97b5b8ab
range: 26ba58610514ac27c86595b01ee657795d382c92..c7e05f406f69253427835628b0639aad97b5b8ab
---

# FASE A.1 — Relatório de execução

## 1. Resumo do que foi feito

O `docker compose up --build` passa a subir de verdade: banco inicializado com
`vector(768)` e índice HNSW de cosseno, backend respondendo através do nginx,
logging estruturado em JSON com `request_id` por requisição, e o envelope de
erro único aplicado por handler global. Ficaram fixados os três contratos que os
dois tracks vão consumir (schema, envelope, formato de log) e os três contratos
de arquitetura, já verificáveis por `make arch`.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `db/001_init.sql` | Schema completo: `documents`, `chunks` com `vector(768)`, `ON DELETE CASCADE`, `unique (session_id, content_hash)` e `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)` |
| `backend/.importlinter` | Os três contratos de §4.8: camadas, núcleo puro e ausência de framework de RAG |
| `backend/app/config.py` | `Settings` cobrindo exatamente o conjunto de `.env.example`; `GEMINI_API_KEY` com default vazio |
| `backend/app/logging_setup.py` | `structlog` com renderer JSON, `configure_logging()`, `get_logger()` e binding/limpeza de `request_id` |
| `backend/app/errors.py` | `AppError` e as cinco subclasses de §4.3, mais os três handlers globais que garantem o envelope |
| `backend/app/main.py` | App, lifespan, middleware, router com `prefix="/api"`, `GET /api/health` e `GET /api/config` |
| `backend/app/core/models.py` | `PageText`, `Chunk` e `DocumentStatus` — todo o vocabulário puro que A.2 e A.4 consomem |
| `backend/app/adapters/db.py` | Pool asyncpg com retry/backoff, verificação de dimensão da coluna e varredura de órfãos |
| `backend/app/api/schemas.py` | `HealthResponse` e `ConfigResponse` |
| `backend/app/api/middleware.py` | `RequestIdMiddleware`: gera/propaga `request_id` e devolve `X-Request-Id` |
| `backend/tests/test_health.py` | Sonda de saúde e presença/preservação do `X-Request-Id` |
| `backend/tests/test_config.py` | Settings carregam sem `.env`; `/api/config` publica os três limites |
| `backend/tests/test_errors.py` | Envelope `{code, message}` nos três caminhos de erro |
| `backend/tests/test_lifespan.py` | Verificação de dimensão (AC-27) e varredura de órfãos (AC-16) |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/app/__init__.py` | Docstring declarando as três camadas e que a direção é verificada por `make arch` |
| `backend/pyproject.toml` | Override de mypy para `asyncpg.*` (`ignore_missing_imports`) — ver desvio 2 abaixo |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** Nada do esqueleto foi reescrito. `docker-compose.yml`,
`backend/Dockerfile`, `frontend/nginx.conf`, `frontend/Dockerfile`, `Makefile`,
`.env.example`, `backend/pyproject.toml` e `backend/uv.lock` foram usados como
estavam. Os seis defeitos de §4.1 continuam corrigidos: o `proxy_pass` sem barra
final foi exercitado (o `curl` através do nginx só responde 200 porque o prefixo
`/api` é preservado), o `client_max_body_size 30m` segue no arquivo, o
`pg_isready -h 127.0.0.1` foi quem liberou o backend nos dois boots a frio, o
`env_file` propagou as 20 variáveis (conferido em `docker compose config`), o
CMD do Dockerfile chama o binário do venv, e o FastAPI resolvido é 0.141.1.

**Decisões de design.**

- `create_app()` é fábrica, e o acesso ao banco passa por uma dependência
  (`get_database`) em vez de import de módulo. É o que permite os testes rodarem
  offline: eles usam `httpx.ASGITransport`, que não dispara o lifespan, e
  injetam um dublê por `dependency_overrides`. Sem isso, nenhum teste de rota
  rodaria sem Postgres, e o gate `make test` viraria obstáculo.
- A dimensão da coluna é lida de `pg_attribute.atttypmod`, que no pgvector
  guarda a dimensão diretamente (sem o deslocamento que `varchar` usa).
  `atttypmod <= 0` é tratado como coluna sem dimensão declarada.
- `sweep_orphans` ficou em `adapters/db.py`, e não numa camada de repositório,
  porque o repositório só nasce na `A.4`. A `A.4` deve consumir este método pelo
  seu `DocumentRepository`, não reimplementar a varredura.

**Desvios da spec — três, todos declarados.**

1. **Arquivo de teste a mais.** A spec listava `test_health`, `test_config` e
   `test_errors`. As verificações de startup (AC-27 dimensão, AC-16 órfãos) não
   são erro de API nem sonda de saúde; pô-las em `test_errors.py` seria nome
   enganoso. Criei `backend/tests/test_lifespan.py`. Nenhum comportamento a mais
   foi implementado — só a organização difere.
2. **`backend/pyproject.toml` alterado.** Não estava na lista de "arquivos
   alterados" da fase. `asyncpg` não publica `py.typed`, e sob `mypy --strict` o
   import falha o gate. A alteração é um `[[tool.mypy.overrides]]` restrito a
   `asyncpg.*` com `ignore_missing_imports`. Nenhuma outra regra do strict foi
   afrouxada — o que a constitution proíbe é afrouxar gate para fazer código
   passar, e aqui o que falta é stub de terceiro.
3. **Gate de conclusão cumprido parcialmente: o serviço `frontend` não subiu com
   o bundle React.** `frontend/Dockerfile` roda `npm run build`, que exige
   `index.html` e `src/main.tsx` — entregáveis da fase **B.1**, executada em
   paralelo por outro agente em outra branch. Nesta branch eles não existem, e
   criá-los seria invadir o escopo do Track B. O que foi provado: os serviços
   `db` e `backend` sobem a frio duas vezes, e o `curl` de `/api/health`
   **atravessa um nginx rodando o `frontend/nginx.conf` commitado**, o que é
   exatamente o roteamento que a A.1 entrega. O override usado para isso vive
   fora do repositório (não é entregável) e também remapeou as portas para
   55432/8100/5273, porque a 5173 estava ocupada pelo container `talkdoc-b1` do
   agente do Track B. **Item para o avaliador:** o `up --build` com os três
   serviços reais só pode ser conferido depois que a B.1 estiver na branch.

Nenhuma violação do escopo travado: não há ORM nem query builder, todo SQL é
parametrizado (`$1`), `DATABASE_URL` e chave não aparecem em resposta nem em
log, `GEMINI_API_KEY` não é obrigatória no import, nenhuma rota de documento foi
criada, nenhum defeito de §4.1 voltou, e todo log passa pelo structlog com
evento nomeado.

## 5. Comandos rodados + saídas reais

```text
# lint — cd backend && uv run ruff check .
All checks passed!

# type-check — cd backend && uv run mypy app
Success: no issues found in 12 source files

# arquitetura — cd backend && uv run lint-imports --config .importlinter
Camadas: api -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Contracts: 3 kept, 0 broken.

# testes — cd backend && uv run pytest -q
................                                                         [100%]
16 passed in 2.11s

# frontend (lint + tsc) — [—] NÃO RODADO
# Justificativa: `npm run lint` e `npx tsc --noEmit` operam sobre frontend/src,
# que nesta branch só tem .gitkeep. O conteúdo é entregável da B.1 (Track B, em
# execução paralela). Rodá-los aqui reprovaria por ausência de código que esta
# fase não deve escrever. Por isso `make check` foi rodado como seus quatro
# gates de backend, e não pelo alvo agregador.

# boot a frio #1 — docker compose down -v && up --build
Container yaitec-talkdoc-tracka-db-1  Healthy
Container yaitec-talkdoc-tracka-backend-1  Started
backend pronto em 3s

$ curl -is http://localhost:5273/api/health     # ATRAVÉS DO NGINX
HTTP/1.1 200 OK
Server: nginx/1.27.5
Content-Type: application/json
x-request-id: 82ca617f-6309-4974-a0b0-8ed31861a211

{"status":"ok","database":"ok"}

$ curl -s http://localhost:5273/api/config
{"max_upload_mb":25,"max_pdf_pages":20,"max_extracted_chars":60000}

# boot a frio #2 — docker compose down -v (volume REMOVIDO) && up --build
Volume yaitec-talkdoc-tracka_pgdata  Removed
Container yaitec-talkdoc-tracka-db-1  Healthy
backend pronto em 2s
HTTP/1.1 200 OK
x-request-id: c81d31d6-f95a-43e0-b714-c45ab3609e30
{"status":"ok","database":"ok"}

# schema real, depois do initdb
$ psql -tAc "\d chunks"
 embedding   | vector(768) |           | not null
Indexes:
    "chunks_embedding_idx" hnsw (embedding vector_cosine_ops)
Foreign-key constraints:
    "chunks_document_id_fkey" FOREIGN KEY (document_id)
        REFERENCES documents(id) ON DELETE CASCADE

# log estruturado emitido pelo container
{"orphans_swept": 0, "event": "app.started", "level": "info",
 "timestamp": "2026-08-17T17:15:05.275169Z"}

# grep de segredo no log capturado (esperado: 0)
$ docker compose logs backend | grep -c 'AQ.Ab8RN6'
0
$ docker compose logs backend | grep -c 'postgresql://'
0
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-14** (`/api/config` devolve os três limites) — `curl` através do
  nginx retornou `{"max_upload_mb":25,"max_pdf_pages":20,"max_extracted_chars":60000}`,
  iguais aos que o servidor aplica. Teste: `test_config_publica_os_tres_limites`.
- [x] **AC-16** (órfão vira `failed` no restart) — verificado **no container**:
  inseri `documents(status='processing')`, reiniciei o backend, e o registro
  passou a `failed` com a mensagem orientando reenviar. Log emitido:
  `{"document_id": "e3da591c-...", "event": "document.orphan_swept",
  "level": "warning"}` seguido de `{"orphans_swept": 1, "event": "app.started"}`.
  Testes offline: `test_varredura_marca_orfaos_como_failed` e o caso sem órfãos.
- [x] **AC-17** (envelope em todo erro, inclusive validação do framework) —
  `test_erro_de_dominio_sai_no_envelope` (413 `arquivo_grande`),
  `test_erro_de_validacao_do_framework_sai_no_envelope` (422 `arquivo_invalido`,
  corpo com exatamente as chaves `code` e `message`) e
  `test_erro_inesperado_nao_vaza_detalhe_interno` (500, e a string interna
  `"detalhe interno"` ausente do corpo).
- [x] **AC-24** (`make arch` reprova import proibido) — os três contratos
  passam (`3 kept, 0 broken`) sobre a estrutura real. *A prova de que o gate
  morde — violação injetada — é entregável da **A.6**, conforme a spec.*
- [x] **AC-26** (`/api/health` 200 através do nginx) — cumprido nos dois boots a
  frio, com `x-request-id` presente na resposta. Ressalva do desvio 3: o nginx
  rodou o `nginx.conf` commitado, mas sem o bundle da B.1.
- [x] **AC-27** (dimensão divergente aborta rápido) — verificado **no
  container**, subindo o backend com `EMBEDDING_DIM=1536`:
  `app.errors.InternalError: EMBEDDING_DIM=1536 diverge da coluna
  chunks.embedding, que tem 768 dimensões. Rode 'make down' e suba de novo.`
  seguido de `ERROR: Application startup failed. Exiting.` Testes offline:
  três casos em `test_lifespan.py`.
- [x] **Settings carregam sem `.env`** — `test_settings_carregam_sem_env`
  constrói `Settings(_env_file=None)` com `GEMINI_API_KEY` removida do ambiente.
- [x] **AC-11 (parcial, o que cabe nesta fase)** — o índice HNSW é
  `vector_cosine_ops` e o `ON DELETE CASCADE` existe, conferidos no banco real.
  As colunas preenchidas por documento processado são da `A.4`/`A.5`.

## 7. Definition of Done da fase

- [x] Testes da fase verdes — 16 passando, offline, sem banco e sem chave.
- [x] Comandos de validação limpos nos arquivos tocados — ruff, mypy strict,
      lint-imports e pytest zerados. Gates de frontend `[—]` justificados (§5).
- [x] Escopo travado respeitado — nenhuma violação BLOQUEANTE da §5.
- [x] Nenhum segredo/PII em log/DTO/exceção — `grep` da chave e de
      `postgresql://` na saída de log do container: 0 ocorrências.
- [x] Commits em pt-BR (Conventional Commits).

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **~~O gate "três serviços a frio" está incompleto por dependência de track.~~
   FECHADO em 2026-08-17, depois do merge do Track B.** Com `frontend/src`
   presente, o `docker compose up --build` foi rodado **duas vezes a frio, com
   os três serviços reais** (sem o override de imagem; só as portas seguem
   remapeadas, porque o Track B ocupa a 5173 e a 8000 nesta máquina):

   ```text
   # boot a frio #1 e #2, cada um depois de `down -v` (volume REMOVIDO)
   db Healthy -> backend Started -> frontend Started      pronto em 3s
   $ curl -is http://localhost:5273/api/health
   HTTP/1.1 200 OK
   x-request-id: 2d5d7e8e-331d-47f4-ba06-bb12e423ec4b
   {"status":"ok","database":"ok"}
   $ curl -s http://localhost:5273/          # a SPA real é servida pelo nginx
   <!doctype html><html lang="pt-BR"> ... <title>TalkDoc — converse com o seu PDF</title>

   # ponta a ponta no stack completo
   POST /api/documents -> 202 {"id":"b16d30ff-...","status":"pending"}
   GET  /api/documents/{id} -> {"status":"ready","page_count":3,
                                "chunks_total":10,"chunks_processed":10}
   chunks | paginas | dims  ->  10 | 3 | 768
   grep da chave no log: 0        grep de 'postgresql://' no log: 0
   ```

   Com isso **AC-26 está integralmente satisfeito** e o desvio 3 da §4 deixa de
   existir. `make check` e `make security` retornam **zero** com os gates de
   frontend incluídos.
2. **`atttypmod` como fonte da dimensão.** Funciona no pgvector 0.8 (conferido
   contra a coluna real, que devolveu 768). Se o avaliador preferir algo menos
   dependente de detalhe interno, a alternativa é `format_type(atttypid,
   atttypmod)` e parse da string — mais robusto a mudança de representação, mais
   frágil a mudança de formatação. Escolhi o inteiro; vale um olhar.
3. **`sweep_orphans` em `adapters/db.py`.** A `A.4` declara `sweep_orphans` no
   protocolo `DocumentRepository`. Deixei a implementação aqui porque o lifespan
   precisa dela agora. Se o avaliador da `A.4` encontrar a lógica duplicada no
   repositório, é regressão — o correto é delegar.
4. **Alteração não declarada em `pyproject.toml`** (desvio 2). Pequena e
   necessária, mas é alteração fora da lista da fase e merece o veredito
   explícito do avaliador.
