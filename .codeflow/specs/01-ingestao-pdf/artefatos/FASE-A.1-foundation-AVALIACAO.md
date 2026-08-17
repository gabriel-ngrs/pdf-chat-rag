---
spec: 01-ingestao-pdf
fase: A.1
slug_fase: foundation
tentativa: 1
veredito: RESSALVAS
score: 9.0
threshold: 8.5
range_avaliado: 26ba58610514ac27c86595b01ee657795d382c92..c7e05f406f69253427835628b0639aad97b5b8ab
---

# FASE A.1 — Avaliação independente

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 9.0 / threshold 8.5

Zero BLOQUEANTES. Dois achados IMPORTANTES: o envelope de erro único **não**
cobre os erros HTTP gerados pelo próprio framework (404 de rota inexistente e
405), contra a letra do AC-17; e um fragmento de 9 caracteres da chave real de
API entrou no histórico versionado pelo relatório desta fase. A fundação em si —
schema, config, logging, contratos de arquitetura — é sólida e foi verificada
contra o banco real.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 4 | AC-14/AC-16/AC-24/AC-26/AC-27 cobertos; AC-17 falha para `HTTPException` do framework — sonda em §6 devolve `{"detail":"Not Found"}` em `/api/rota-que-nao-existe` |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `lint-imports` 4/4 KEPT (§6); `create_app()` fábrica + `get_database` como dependência (`app/main.py:28-40`) é o que torna a suíte offline possível |
| 3 | Segurança / LGPD / multi-tenant | 3 | 3 | Código limpo: `git grep` de chave em arquivos versionados só encontra as falsas dos testes; **mas** `d6f42d3` gravou `grep -c 'AQ.Ab8RN6'` — 9 caracteres da chave real — no relatório desta fase |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Esqueleto reusado sem reescrita; os seis defeitos de §4.1 seguem corrigidos (`frontend/nginx.conf:16-25`, `docker-compose.yml:20`, `backend/pyproject.toml:9`) |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `AppError` com `code`/`status_code` por subclasse (`app/errors.py:17-96`); `DocumentStatus` como `StrEnum`; dataclasses `frozen`/`slots` |
| 6 | Local e nomes dos arquivos | 2 | 5 | Bate com a lista da §5 da spec; `tests/test_lifespan.py` a mais, declarado e bem nomeado |
| 7 | Qualidade de código | 2 | 5 | Docstrings dizem "por quê" (ex.: `app/adapters/db.py:56-62` justifica o retry pelo boot a frio); funções curtas; sem comentário de "o que faz" |
| 8 | Testes e cobertura | 2 | 4 | 16 testes offline cobrindo os ACs da fase; falta o caso que teria pegado o furo do AC-17 (erro HTTP do framework, não de validação) |
| 9 | Migration safety | 2 | 5 | `db/001_init.sql:1-3` declara que só roda em banco vazio; `make down` remove o volume; verificado contra Postgres real (§6) |

Média ponderada: 99/110 → **9.0**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

### I-1 · O envelope único não vale para os erros HTTP do framework — `backend/app/errors.py:139-141`

O AC-17 diz "*Dado **qualquer** erro 4xx/5xx, então o corpo tem exatamente
`{code, message}`*". Estão registrados três handlers: `AppError`,
`RequestValidationError` e `Exception`. Falta o de `StarletteHTTPException`, que
é quem responde 404 de rota inexistente, 405 de método errado e qualquer
`HTTPException` levantada pelo framework. Medido (§6):

```
GET    /api/rota-que-nao-existe   -> 404  chaves=['detail']  {"detail":"Not Found"}
DELETE /api/config                -> 405  chaves=['detail']  {"detail":"Method Not Allowed"}
```

O relatório marca AC-17 como `[x]` com a justificativa "envelope em todo erro",
o que é mais forte do que o código sustenta. O impacto prático hoje é baixo (a
SPA não chama rota inexistente), mas o contrato de §4.3 é fonte única dos dois
tracks e a `FEAT-0002` vai consumi-lo por SSE, onde não há status para o cliente
cair de volta.

**Correção sugerida:** registrar mais um handler no mesmo lugar —

```python
from starlette.exceptions import HTTPException as StarletteHTTPException

async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    status = getattr(exc, "status_code", 500)
    code = {404: NotFoundError.code, 413: FileTooLargeError.code}.get(status, InternalError.code)
    return JSONResponse(status_code=status, content=error_body(code, "<mensagem pt-BR>"))

app.add_exception_handler(StarletteHTTPException, handle_http_error)
```

mais um teste em `tests/test_errors.py` para 404 de rota e 405.

### I-2 · Fragmento da chave real de API no histórico versionado — `d6f42d3` (relatório desta fase)

A constitution do projeto é explícita: "`GEMINI_API_KEY` nunca aparece em
código, em log ou **em arquivo versionado**". O commit `d6f42d3` colou
`docker compose logs backend | grep -c 'AQ.Ab8RN6'` no relatório — 9 caracteres
literais da chave real, acima do limiar de 8 que o próprio projeto trata como
fragmento identificável (`app/logging_setup.py:28`). O `34cb479` trocou o trecho
por `$GEMINI_API_KEY` na ponta, mas o histórico é entregável: o repositório vai
para o avaliador com o commit intacto.

**Correção sugerida:** **rotacionar a chave** — é a única remediação real de um
segredo exposto, e vale independentemente de reescrever ou não a história (a
chave também transitou por chats). Reescrever `dev` não é recomendado com o
Track B já mergeado; se o owner quiser a história limpa, o momento é antes de
adicionar o colaborador ao repositório privado, com `git filter-repo` sobre o
arquivo e force-push coordenado.

## 5. Sugestões

- `handle_validation_error` (`app/errors.py:119`) descarta `exc` inteiro. A
  mensagem genérica é a decisão certa para o usuário, mas registrar os campos
  inválidos **no log** (não na resposta) custa uma linha e economiza diagnóstico.
- `atttypmod` como fonte da dimensão (item 2 da §9 do relatório): funciona e está
  provado contra o pgvector 0.8 real. Mantenha — a alternativa por
  `format_type()` troca fragilidade de representação por fragilidade de string.
- `Database.connect` (`app/adapters/db.py:71`) encadeia a exceção original com
  `from exc`. Nenhum DSN apareceu nos testes, mas a redação de segredo da A.6 não
  cobre `DATABASE_URL`; vale um teste que prove que a falha de conexão não
  imprime o DSN.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor c7e05f40... HEAD   -> OK (ancestral de 34cb479)
$ git status --porcelain                          -> (vazio; árvore limpa ao fim)

$ cd backend && uv run ruff check .
All checks passed!

$ uv run mypy app
Success: no issues found in 18 source files

$ uv run lint-imports --config .importlinter
Analyzed 40 files, 81 dependencies.
Camadas: main -> api -> ingestion -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Sem ORM nem query builder KEPT
Contracts: 4 kept, 0 broken.

$ env -u GEMINI_API_KEY DATABASE_URL='postgresql://ninguem@127.0.0.1:1/x' uv run pytest -q
119 passed, 6 deselected in 6.99s
Required test coverage of 90% reached. Total coverage: 98.98%
```

**Schema conferido contra um Postgres descartável, subido por mim a partir de
`db/001_init.sql` (container removido ao fim):**

```text
$ docker exec ... psql -U talkdoc -d talkdoc -c '\d chunks'
 embedding   | vector(768) |           | not null
Indexes:
    "chunks_embedding_idx" hnsw (embedding vector_cosine_ops)
Foreign-key constraints:
    "chunks_document_id_fkey" FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE

$ uv run pytest -m db -q
6 passed, 119 deselected in 0.77s
```

**Sonda do envelope (AC-17), escrita por mim:**

```text
GET    /api/rota-que-nao-existe         -> 404  chaves=['detail']  {"detail":"Not Found"}
GET    /nao-existe                      -> 404  chaves=['detail']  {"detail":"Not Found"}
DELETE /api/config                      -> 405  chaves=['detail']  {"detail":"Method Not Allowed"}
```

**Segredo em arquivos versionados:**

```text
$ git grep -nIE "AIza[0-9A-Za-z_-]{10,}" -- .
backend/tests/test_ingestion_api.py:30:FAKE_KEY = "AIzaSyD-chave-falsa-para-teste-..."
backend/tests/test_logging.py:26:FAKE_KEY = "AIzaSyD-chave-falsa-para-teste-..."
(só chaves falsas de teste)

$ git show 34cb479 | grep '^-.*grep'
-$ docker compose logs backend | grep -c 'AQ.Ab8RN6'      <- fragmento real, vivo em d6f42d3
```

**Gates de frontend:** `npm run lint` e `npx tsc --noEmit` retornam zero na ponta
da branch (rodados por mim; hoje já existe `frontend/src` vindo do Track B).

**`docker compose up --build` a frio — `[—]` NÃO RODADO por mim.** O serviço
`backend` do compose exige `GEMINI_API_KEY` (`docker-compose.yml:31`,
`env_file: .env`), e a constitution proíbe o avaliador criar ou modificar `.env`.
O que verifiquei diretamente: o `db/001_init.sql` produz o schema esperado num
Postgres a frio (saída acima) e o `frontend/nginx.conf` preserva o prefixo
`/api` sem barra final. A evidência dos dois boots a frio com os três serviços
permanece a do executor (§9 do relatório), não reproduzida aqui.

## 7. Itens da fase / DoD não atendidos

- **AC-17 parcial** (I-1): erros HTTP do framework fora do envelope.
- Nada mais. O gate de conclusão da fase (compose a frio ×2, `/api/health` 200
  pelo nginx com `X-Request-Id`, `make check` zero) está atendido pela evidência
  do executor e não foi contraditado por nada que eu tenha medido.

## 8. Divergências entre o relatório e o código real

1. **AC-17 marcado como atendido** ("envelope em todo erro, inclusive validação
   do framework") — o código cobre `AppError`, `RequestValidationError` e
   `Exception`, mas não `HTTPException`. A afirmação é mais ampla que a
   implementação.
2. **§4 afirma "chave não aparece em resposta nem em log"** — verdadeiro para o
   código; o próprio relatório, porém, carregou o fragmento para o histórico
   (I-2). O commit `34cb479` corrige o texto, não o histórico.
3. Tudo o mais confere: 16 testes, os três handlers, o pool com retry, a
   verificação de dimensão, a varredura de órfãos, e o desvio declarado no
   `pyproject.toml` (override de `asyncpg.*` no mypy) — que é ausência de stub de
   terceiro, não afrouxamento de gate.
