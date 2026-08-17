.PHONY: check lint typecheck test security up down logs

check: lint typecheck test

lint:
	cd backend && uv run ruff check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy app
	cd frontend && npx tsc --noEmit

test:
	cd backend && uv run pytest

security:
	cd backend && uv run pip-audit
	cd frontend && npm audit

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f
