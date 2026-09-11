---
versão: 1.0
status: estável
atualizado: 2026-08-17
projeto: talkdoc
---

# Constitution do projeto: talkdoc

## Stack

- **Linguagem (backend):** Python 3.12+
- **Framework web:** FastAPI + uvicorn
- **Gerenciador de pacotes:** uv (`pyproject.toml` + `uv.lock`)
- **Banco / vector store:** PostgreSQL 16 com extensão pgvector (driver: asyncpg, SQL escrito à mão)
- **IA:** SDK `google-genai` — Gemini para geração e para embeddings; pipeline de RAG próprio, sem framework
- **Extração de PDF:** pypdf
- **Linguagem (frontend):** TypeScript 5.7+
- **Frontend:** React 19 + Vite 6 + Tailwind CSS 4, servido por nginx
- **Testes:** pytest + pytest-asyncio + httpx
- **Linter/formatter:** ruff (backend), eslint (frontend)
- **Type checker:** mypy strict (backend), tsc strict (frontend)
- **Orquestração:** Docker Compose (db + backend + frontend)

## Padrão arquitetural

**Layered (camadas)** com dependências fluindo para dentro. Três níveis no backend:

- `backend/app/core/` — domínio puro: chunking, montagem de prompt, condensação de pergunta de continuação, seleção de top-k. Sem I/O.
- `backend/app/adapters/` — implementações concretas: cliente Gemini, repositório Postgres, extrator de PDF.
- `backend/app/api/` — pontos de entrada: rotas FastAPI e schemas de request/response.

`api/` depende de `adapters/`, `adapters/` depende de `core/`. Nunca o contrário.

No frontend, `frontend/src/` separa `components/` (apresentação), `hooks/` (estado e efeitos) e `lib/` (cliente HTTP e tipos).

## Regras invariantes específicas

- Nenhum módulo em `backend/app/core/` importa `fastapi`, `asyncpg` ou `google.genai`. Verificável por inspeção dos imports do pacote.
- **Frameworks de RAG são proibidos** — `langchain`, `llama-index` e equivalentes não entram nas dependências. O pipeline (chunking, embeddings, retrieval, prompt) é escrito no projeto. Decisão da Fase 2 do bootstrap.
- Toda resposta do chat retorna citações estruturadas com número de página e trecho de origem, em campo próprio do payload — não apenas embutidas no texto gerado.
- Quando nenhum chunk recuperado passa do limiar de similaridade, a API responde com recusa explícita ("não encontrei isso no documento") em vez de gerar resposta sem fundamento no PDF.
- Segredos vivem apenas em variáveis de ambiente. `GEMINI_API_KEY` nunca aparece em código, em log ou em arquivo versionado; `.env` está no `.gitignore` e `.env.example` traz a chave vazia.
- Mensagens de erro voltadas ao usuário final, textos da UI e o `README.md` são em pt-BR.
- `mypy` roda em modo strict sobre `backend/app`, e `tsc` em modo strict sobre `frontend/src`. Nenhum gate é afrouxado para fazer código passar.
- A partir de um clone limpo, `cp .env.example .env` (com a chave preenchida) seguido de `docker compose up --build` sobe a aplicação inteira. Requisito de entrega do escopo, não conveniência.

## Áreas de alto risco

- **`backend/app/core/`** — é o núcleo avaliado do RAG. Mudança em chunking, retrieval, limiar de similaridade ou montagem de prompt exige teste unitário determinístico, sem rede e sem banco.
- **`backend/app/adapters/`** (cliente Gemini) — toda chamada externa tem retry com backoff e timeout explícito; embeddings de documento vão em lote, nunca uma requisição por chunk. A chave de API nunca é logada, nem em mensagem de exceção.
- **`db/`** — os scripts SQL só rodam em banco vazio (`docker-entrypoint-initdb.d`). Alterar o schema exige `make down` (que remove o volume) antes do próximo `up`, senão a mudança é silenciosamente ignorada.
- **`docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`** — sustentam o critério "roda de primeira". Qualquer mudança aqui é validada com um `docker compose up --build` completo antes de commit.

## Definition of Done específica

Itens adicionais ao Definition of Done padrão (constitution universal):

- `make check` retornou zero (ruff + mypy strict + tsc + pytest).
- Toda função nova em `backend/app/core/` tem teste unitário que roda sem rede e sem banco.
- Mudança que afete a experiência de upload ou de chat foi verificada com `docker compose up --build` a partir do estado limpo.
- Decisão de arquitetura nova ou alterada foi refletida na seção `## Arquitetura` do `README.md` — é entregável explícito do escopo.
