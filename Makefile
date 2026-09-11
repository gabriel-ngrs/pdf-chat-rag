.PHONY: check lint typecheck arch test test-db security eval up dev down stop logs

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
# Os dois lados entram: uma suíte que cobre metade do projeto deixa o `check`
# ficar verde com a outra metade vermelha.
test:
	cd backend && uv run pytest
	cd frontend && npm run test

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

# Modo de desenvolvimento: o código do host é montado nos containers e uma
# edição salva aparece sem rebuild — Vite com HMR no frontend, uvicorn com
# --reload no backend. Mesmas portas do `up`.
#
# O `up` continua sendo o caminho de quem só quer rodar o projeto: nginx
# servindo o build estático, que é o que se entrega. Os dois não sobem juntos
# (disputam a 5173) — pare um antes de subir o outro.
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Para os serviços preservando os dados.
stop:
	docker compose down

# ATENÇÃO: remove o volume do Postgres. Necessário após mudança de schema,
# porque os scripts de db/ só rodam em banco vazio.
down:
	docker compose down -v

logs:
	docker compose logs -f
