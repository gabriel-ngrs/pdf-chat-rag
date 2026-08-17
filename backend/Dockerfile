FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Camada de dependências: invalida só quando o pyproject/lock muda.
# --frozen exige o uv.lock commitado, o que torna o build reprodutível.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# tests/ e eval/ entram na imagem para permitir rodar a suíte e o make eval
# dentro do container (docker compose run --rm backend ...).
COPY app ./app
COPY tests ./tests
COPY eval ./eval

EXPOSE 8000

# Chama o binário do venv diretamente: `uv run` ressincronizaria o grupo dev
# a cada start do container, baixando pytest/mypy/ruff antes de subir a API.
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
