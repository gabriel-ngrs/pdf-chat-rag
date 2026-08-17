---
versão: 1.3
status: estável
atualizado: 2026-08-17
projeto: talkdoc
last_validated: 2026-08-17
validation_hash: 9277700a57e1d32df43b7d7320f3825bde8623322c2597bf613f4d0f08eed012
---

# Manifest do projeto: talkdoc

## Stack identificada

- **Backend:** Python 3.12, FastAPI 0.141.1 (floor `>=0.135`, por causa do SSE nativo), uvicorn 0.32+
- **Gerenciador de pacotes:** uv 0.9.5, com `[tool.uv] package = false` e `uv.lock` commitado
- **Banco / vector store:** PostgreSQL 16 via `pgvector/pgvector:pg16` (pgvector 0.8.x), driver asyncpg 0.30+
- **IA:** SDK `google-genai` — `gemini-embedding-001` a 768 dimensões e `gemini-3.6-flash` para geração (o `gemini-2.5-flash` do desenho original saiu do ar para chaves novas durante a `FEAT-0002`; medido no gate da fase A.4)
- **Extração de PDF:** pypdf 5.1+
- **Validação de dados:** pydantic 2.9+, pydantic-settings 2.6+
- **Frontend:** TypeScript 5.7, React 19, Vite 6, Tailwind CSS 4, nginx 1.27-alpine, `package-lock.json` commitado
- **Testes:** pytest 8.3+, pytest-asyncio 0.24+, httpx 0.27+
- **Logging:** structlog 26.1.0 (renderer JSON)
- **Arquitetura:** import-linter 2.13 (contratos em `backend/.importlinter`)
- **Segurança estática:** bandit 1.9.4
- **Design system:** shadcn/ui sobre Radix, componentes copiados para `frontend/src/components/ui/`
- **Linter:** ruff 0.8+ (line-length 100), eslint 9 + typescript-eslint 8
- **Type checker:** mypy 1.13+ (strict), tsc 5.7 (strict)
- **Auditoria:** pip-audit 2.7+, npm audit
- **Orquestração:** Docker Compose — `db` (porta 5432 publicada para testes e eval), `backend`, `frontend`

## Comandos de validação

| Gate        | Comando real do projeto                                              | Status |
|-------------|-----------------------------------------------------------------------|--------|
| `check`     | `make check` (agrega `lint`, `typecheck`, `arch`, `test`)            | ✓      |
| `lint`      | `cd backend && uv run ruff check .` + `cd frontend && npm run lint`   | ✓      |
| `typecheck` | `cd backend && uv run mypy app` + `cd frontend && npx tsc --noEmit`   | ✓      |
| `arch`      | `cd backend && uv run lint-imports --config .importlinter`            | ✓      |
| `test`      | `cd backend && uv run pytest` + `cd frontend && npm run test` (offline; exclui o marker `db`) | ✓ |
| `security`  | `bandit -r app` + `pip-audit` + `npm audit --audit-level=high`        | ✓      |

Comandos auxiliares fora dos gates: `make test-db` (testes que exigem o Postgres do compose), `make eval` (mede o retrieval; consome quota real, por isso fora do `check`), `make up`, `make stop` (preserva dados), `make down` (**remove o volume**), `make logs`.

## Padrões definidos

- **Camadas com dependência para dentro (meta):** `api/` → `adapters/` → `core/` em `backend/app/`, a estabelecer conforme os módulos forem criados. `core/` definido como núcleo puro, sem I/O.
- **Pipeline de RAG próprio (meta):** chunking, embeddings, retrieval e montagem de prompt implementados no projeto, sem framework de RAG.
- **Chunking por página (meta):** nenhum chunk cruza fronteira de página — é o que torna a citação exata por construção.
- **Envelope de erro único (meta):** toda resposta de erro da API sai como `{code, message}`, e o frontend mapeia por `code`, nunca por status.
- **Logging estruturado (meta):** todo evento em JSON com `timestamp`, `level`, `event` e `request_id`; nomes de evento catalogados nas specs; segredo e conteúdo de documento nunca entram no log.
- **Gates executáveis (meta):** os princípios invioláveis viram comando — `make arch` reprova import proibido em `core/`, `make security` roda análise estática e auditoria de dependências.
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

- Projeto criado em 2026-08-17 pela meta-skill `bootstrap`; manifest atualizado no mesmo dia após a revisão adversarial das specs (ver `decisions/INDEX.md`) e de novo ao fim da `FEAT-0001`.
- **Os padrões acima deixaram de ser prospectivos em 2026-08-17**, com a `FEAT-0001` concluída: as dez fases foram executadas e aprovadas por avaliação independente (`specs/01-ingestao-pdf/artefatos/`). As marcas "(meta)" permanecem no texto porque a seção foi escrita por `bootstrap`; o que era desenho agora é código, e três dos padrões viraram gate executável — camadas e núcleo puro por `make arch` (contrato provado por violação injetada), segredo fora do log por teste, e cobertura de `core/` por `--cov-fail-under=90`.
- Requisitos derivados de `Desafio-Tecnico-TalkDoc-Gabriel-Negreiros-Saraiva.pdf`.
- Seis defeitos de infraestrutura do esqueleto original foram corrigidos e verificados: prefixo do `proxy_pass`, `client_max_body_size`, `pg_isready -h`, `env_file` no compose, `uv run` no CMD do Dockerfile, e o floor do FastAPI. Detalhe em `specs/01-ingestao-pdf/SPEC_01_INGESTAO_PDF.md` §4.
- Verificado no ambiente: `fastapi.sse.EventSourceResponse` e `ServerSentEvent` existem em 0.141.1; o `env_file` propaga as variáveis ao container (`docker compose config`).
- Os cinco gates estão verdes com conteúdo real: 135 testes de backend offline (sem `GEMINI_API_KEY`, sem banco), 40 de frontend, 6 sob o marker `db`, `lint-imports` com 4 contratos e `make security` sem achado alto. A suíte do frontend entrou no `make test` durante o rework do Track B — um `check` que cobre metade do projeto deixa a outra metade ficar vermelha em silêncio.
- Dependências acrescentadas durante a `FEAT-0001`, além do que a stack declarava: `pytest-cov` (gate de cobertura), `httpx` promovida a dependência direta do backend (o adapter de embeddings importa `httpx.TransportError` para reconhecer a falha de transporte do cliente real), e `vitest` + `@testing-library/react` no frontend.
- `FEAT-0003` (biblioteca de documentos) foi cortada do escopo — ver `decisions/2026-08-17-revisao-adversarial-das-specs.md`.
