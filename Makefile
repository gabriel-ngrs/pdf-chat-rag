.PHONY: check lint typecheck arch test test-db security eval up down stop logs

# Gate agregador: é o que precisa estar verde para uma fase fechar.
check: lint typecheck arch test

lint:
	cd backend && uv run ruff check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy app
	cd frontend && npx tsc --noEmit

# Valida a arquitetura em camadas: core/ não pode importar I/O.
# As regras vivem em backend/.importlinter.
arch:
	cd backend && uv run lint-imports --config .importlinter

# Suíte offline: sem rede, sem banco, sem GEMINI_API_KEY.
test:
	cd backend && uv run pytest

# Testes que exigem o Postgres do compose (marcados com @pytest.mark.db).
# Rode `make up` antes.
test-db:
	cd backend && uv run pytest -m db

# Análise estática de segurança + auditoria de dependências.
security:
	cd backend && uv run bandit -q -r app
	cd backend && uv run pip-audit
	cd frontend && npm audit --audit-level=high

# Mede a qualidade do retrieval. Consome quota real da API, por isso fica
# fora do `check`. Exige o compose no ar e a GEMINI_API_KEY definida.
eval:
	cd backend && uv run python -m eval.run_eval

up:
	docker compose up --build

# Para os serviços preservando os dados.
stop:
	docker compose down

# ATENÇÃO: remove o volume do Postgres. Necessário após mudança de schema,
# porque os scripts de db/ só rodam em banco vazio.
down:
	docker compose down -v

logs:
	docker compose logs -f
