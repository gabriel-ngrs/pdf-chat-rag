---
versão: 1.1
status: estável
atualizado: 2026-08-17
projeto: talkdoc
last_validated: 2026-08-17
validation_hash: 9ec803f4c1aac50da65d494296e8fa75dc93ea4e502aafe1350f5d802ae474b3
---

# Manifest do projeto: talkdoc

## Stack identificada

- **Backend:** Python 3.12, FastAPI 0.141.1 (floor `>=0.135`, por causa do SSE nativo), uvicorn 0.32+
- **Gerenciador de pacotes:** uv 0.9.5, com `[tool.uv] package = false` e `uv.lock` commitado
- **Banco / vector store:** PostgreSQL 16 via `pgvector/pgvector:pg16` (pgvector 0.8.x), driver asyncpg 0.30+
- **IA:** SDK `google-genai` — `gemini-embedding-001` a 768 dimensões e `gemini-2.5-flash` para geração
- **Extração de PDF:** pypdf 5.1+
- **Validação de dados:** pydantic 2.9+, pydantic-settings 2.6+
- **Frontend:** TypeScript 5.7, React 19, Vite 6, Tailwind CSS 4, nginx 1.27-alpine, `package-lock.json` commitado
- **Testes:** pytest 8.3+, pytest-asyncio 0.24+, httpx 0.27+
- **Linter:** ruff 0.8+ (line-length 100), eslint 9 + typescript-eslint 8
- **Type checker:** mypy 1.13+ (strict), tsc 5.7 (strict)
- **Auditoria:** pip-audit 2.7+, npm audit
- **Orquestração:** Docker Compose — `db` (porta 5432 publicada para testes e eval), `backend`, `frontend`

## Comandos de validação

| Gate        | Comando real do projeto                                              | Status |
|-------------|-----------------------------------------------------------------------|--------|
| `check`     | `make check` (agrega `lint`, `typecheck`, `test`)                    | ✓      |
| `lint`      | `cd backend && uv run ruff check .` + `cd frontend && npm run lint`   | ✓      |
| `typecheck` | `cd backend && uv run mypy app` + `cd frontend && npx tsc --noEmit`   | ✓      |
| `test`      | `cd backend && uv run pytest` (offline; exclui o marker `db`)         | ✓      |
| `security`  | `cd backend && uv run pip-audit` + `cd frontend && npm audit`         | ✓      |

Comandos auxiliares fora dos gates: `make test-db` (testes que exigem o Postgres do compose), `make eval` (mede o retrieval; consome quota real, por isso fora do `check`), `make up`, `make stop` (preserva dados), `make down` (**remove o volume**), `make logs`.

## Padrões definidos

- **Camadas com dependência para dentro (meta):** `api/` → `adapters/` → `core/` em `backend/app/`, a estabelecer conforme os módulos forem criados. `core/` definido como núcleo puro, sem I/O.
- **Pipeline de RAG próprio (meta):** chunking, embeddings, retrieval e montagem de prompt implementados no projeto, sem framework de RAG.
- **Chunking por página (meta):** nenhum chunk cruza fronteira de página — é o que torna a citação exata por construção.
- **Envelope de erro único (meta):** toda resposta de erro da API sai como `{code, message}`, e o frontend mapeia por `code`, nunca por status.
- **Padrão de testes (meta):** um arquivo por módulo público de `core/`, em `backend/tests/`; a suíte do `make test` roda offline, com fakes de repositório e de provedor. Testes que exigem banco ficam sob o marker `db`.
- **Formato de imports (meta):** imports absolutos a partir de `app`. Sem imports relativos.
- **Schema de banco (meta):** DDL em `db/*.sql` aplicados pelo `docker-entrypoint-initdb.d`; sem ferramenta de migração. `ON DELETE CASCADE` declarado por quem cria a tabela.
- **Organização do frontend (meta):** `components/`, `hooks/` e `lib/` sob `frontend/src/`.

## Arquivos críticos para freshness

Hash `validation_hash` é computado sobre os arquivos abaixo, na ordem:

- `Makefile`
- `backend/pyproject.toml`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `docker-compose.yml`

## Notas de inspeção

- Projeto criado em 2026-08-17 pela meta-skill `bootstrap`; manifest atualizado no mesmo dia após a revisão adversarial das specs (ver `decisions/INDEX.md`).
- Os padrões acima seguem **prospectivos**: são metas de desenho, não observações de código. Não há código de aplicação ainda.
- Requisitos derivados de `Desafio-Tecnico-TalkDoc-Gabriel-Negreiros-Saraiva.pdf`.
- Seis defeitos de infraestrutura do esqueleto original foram corrigidos e verificados: prefixo do `proxy_pass`, `client_max_body_size`, `pg_isready -h`, `env_file` no compose, `uv run` no CMD do Dockerfile, e o floor do FastAPI. Detalhe em `specs/01-ingestao-pdf/SPEC_01_INGESTAO_PDF.md` §4.
- Verificado no ambiente: `fastapi.sse.EventSourceResponse` e `ServerSentEvent` existem em 0.141.1; o `env_file` propaga as variáveis ao container (`docker compose config`).
- Os cinco gates têm comando real, mas ainda não há o que validar: `pytest` retorna exit 5 (nenhum teste coletado). `security` exige `uv sync` e `npm install`.
- `FEAT-0003` (biblioteca de documentos) foi cortada do escopo — ver `decisions/2026-08-17-revisao-adversarial-das-specs.md`.
