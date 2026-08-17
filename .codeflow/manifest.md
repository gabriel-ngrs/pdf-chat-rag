---
versão: 1.0
status: estável
atualizado: 2026-08-17
projeto: talkdoc
last_validated: 2026-08-17
validation_hash: c9a3ba5334523c496f8b788c8d34280af2ecb7241fcce64ace77d3ba1cb61695
---

# Manifest do projeto: talkdoc

## Stack identificada

- **Backend:** Python 3.12, FastAPI 0.115+, uvicorn 0.32+ (standard)
- **Gerenciador de pacotes:** uv, com `[tool.uv] package = false`
- **Banco / vector store:** PostgreSQL 16 via imagem `pgvector/pgvector:pg16`, driver asyncpg 0.30+
- **IA:** SDK `google-genai` 0.3+ — Gemini para geração e embeddings
- **Extração de PDF:** pypdf 5.1+
- **Validação de dados:** pydantic 2.9+, pydantic-settings 2.6+
- **Frontend:** TypeScript 5.7, React 19, Vite 6, Tailwind CSS 4, nginx 1.27-alpine
- **Testes:** pytest 8.3+, pytest-asyncio 0.24+, httpx 0.27+
- **Linter:** ruff 0.8+ (line-length 100), eslint 9 + typescript-eslint 8
- **Type checker:** mypy 1.13+ (strict), tsc 5.7 (strict)
- **Auditoria:** pip-audit 2.7+, npm audit
- **Orquestração:** Docker Compose — serviços `db`, `backend`, `frontend`

## Comandos de validação

| Gate        | Comando real do projeto                                   | Status |
|-------------|-----------------------------------------------------------|--------|
| `check`     | `make check` (agrega `lint`, `typecheck`, `test`)         | ✓      |
| `lint`      | `cd backend && uv run ruff check .` + `cd frontend && npm run lint` | ✓ |
| `typecheck` | `cd backend && uv run mypy app` + `cd frontend && npx tsc --noEmit` | ✓ |
| `test`      | `cd backend && uv run pytest`                             | ✓      |
| `security`  | `cd backend && uv run pip-audit` + `cd frontend && npm audit` | ✓  |

## Padrões definidos

- **Camadas com dependência para dentro (meta):** `api/` → `adapters/` → `core/` em `backend/app/`, a estabelecer conforme os módulos forem criados. `core/` definido como núcleo puro, sem I/O.
- **Pipeline de RAG próprio (meta):** chunking, embeddings, retrieval top-k e montagem de prompt implementados no projeto, sem framework de RAG — decisão da Fase 2, ainda não materializada.
- **Padrão de testes (meta):** um arquivo de teste por módulo público de `core/`, em `backend/tests/`, espelhando a estrutura do pacote; nomenclatura `test_<modulo>.py`. Testes de `core/` definidos como offline (sem rede, sem banco).
- **Formato de imports (meta):** imports absolutos a partir de `app`. Sem imports relativos.
- **Schema de banco (meta):** DDL em arquivos `.sql` sob `db/`, aplicados pelo `docker-entrypoint-initdb.d` do Postgres; sem ferramenta de migração.
- **Organização do frontend (meta):** `components/`, `hooks/` e `lib/` sob `frontend/src/`, a estabelecer na primeira feature.

## Arquivos críticos para freshness

Hash `validation_hash` é computado sobre os arquivos abaixo, na ordem:

- `Makefile`
- `backend/pyproject.toml`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `docker-compose.yml`

## Notas de inspeção

- Projeto criado em 2026-08-17 pela meta-skill `bootstrap`, em modo em-projeto (a raiz já continha os PDFs do desafio e o `.codeflow/` do `install.sh`).
- Os padrões da seção acima são **prospectivos**: metas decididas na Fase 2, não observações de código. Nenhum código de aplicação existe ainda.
- Requisitos derivados de `Desafio-Tecnico-TalkDoc-Gabriel-Negreiros-Saraiva.pdf`, não de `roteiro.md` — não houve `/ideacao`.
- Os cinco gates têm comando real configurado, mas ainda não há o que validar: `pytest` retorna exit 5 (nenhum teste coletado) e `ruff`/`mypy` percorrem pacotes vazios. `security` exige as dependências instaladas (`uv sync`, `npm install`).
- `backend/Dockerfile` aponta para `app.main:app`, módulo ainda inexistente — `docker compose up` só sobe de fato após a primeira fase de execução da spec.
- Ids de modelo Gemini (embeddings e geração) ainda não fixados no código; a confirmar contra a documentação vigente na implementação.
