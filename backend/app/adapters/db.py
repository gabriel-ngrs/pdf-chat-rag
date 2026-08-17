"""Acesso ao PostgreSQL via asyncpg.

SQL é escrito à mão e sempre parametrizado — não há ORM nem query builder no
projeto. Este módulo concentra o ciclo de vida do pool e as duas verificações
que o lifespan faz antes de o app aceitar tráfego.
"""

import asyncio
from typing import Any

import asyncpg

from app.errors import InternalError
from app.logging_setup import get_logger

logger = get_logger(__name__)

CONNECT_TIMEOUT_SECONDS = 30.0
_INITIAL_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 4.0

_SWEEP_ORPHANS_SQL = """
    UPDATE documents
       SET status = 'failed',
           error_message = $1
     WHERE status IN ('pending', 'processing')
 RETURNING id
"""

_EMBEDDING_TYPMOD_SQL = """
    SELECT atttypmod
      FROM pg_attribute
     WHERE attrelid = 'chunks'::regclass
       AND attname = 'embedding'
"""

ORPHAN_MESSAGE = (
    "O processamento foi interrompido por um reinício do servidor. Envie o arquivo de novo."
)


class Database:
    """Pool de conexões e as operações de infraestrutura do startup."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool[Any] | None = None

    @property
    def pool(self) -> "asyncpg.Pool[Any]":
        """Pool já conectado. Erro de programação se acessado antes do lifespan."""
        if self._pool is None:
            raise RuntimeError("O pool de conexões ainda não foi criado.")
        return self._pool

    async def connect(self, timeout_seconds: float = CONNECT_TIMEOUT_SECONDS) -> None:
        """Cria o pool, re-tentando com backoff até `timeout_seconds`.

        O retry não é zelo excessivo: o healthcheck do Postgres pode liberar o
        backend poucos instantes antes de o servidor aceitar conexão TCP, e sem
        ele o uvicorn morre num `docker compose up` a frio.
        """
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        backoff = _INITIAL_BACKOFF_SECONDS
        while True:
            try:
                self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=10)
                return
            except (OSError, asyncpg.PostgresError) as exc:
                if asyncio.get_running_loop().time() >= deadline:
                    raise InternalError("Não foi possível conectar ao banco de dados.") from exc
                logger.warning("database.connect_retry", backoff_seconds=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    async def close(self) -> None:
        """Fecha o pool, se existir."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> bool:
        """Confirma que o banco responde. É o que a sonda de saúde consulta."""
        try:
            await self.pool.fetchval("SELECT 1")
        except (OSError, asyncpg.PostgresError, RuntimeError):
            return False
        return True

    async def embedding_dimension(self) -> int:
        """Lê a dimensão real declarada na coluna `chunks.embedding`.

        No pgvector o `atttypmod` guarda a dimensão diretamente, sem o
        deslocamento que tipos como `varchar` usam.
        """
        typmod = await self.pool.fetchval(_EMBEDDING_TYPMOD_SQL)
        if typmod is None or int(typmod) <= 0:
            raise InternalError("A coluna chunks.embedding não declara dimensão.")
        return int(typmod)

    async def verify_embedding_dimension(self, expected: int) -> None:
        """Aborta o startup se a configuração divergir do schema já criado.

        Divergir aqui produziria falha só no momento de inserir o primeiro
        vetor, depois de já ter queimado quota embedando o documento inteiro.
        """
        actual = await self.embedding_dimension()
        if actual != expected:
            raise InternalError(
                f"EMBEDDING_DIM={expected} diverge da coluna chunks.embedding, "
                f"que tem {actual} dimensões. Rode `make down` e suba de novo."
            )

    async def sweep_orphans(self) -> int:
        """Marca como `failed` os documentos presos em `pending` ou `processing`.

        Uma task de background não sobrevive a um restart do processo; sem esta
        varredura o documento ficaria para sempre "processando" na tela.
        """
        rows = await self.pool.fetch(_SWEEP_ORPHANS_SQL, ORPHAN_MESSAGE)
        for row in rows:
            logger.warning("document.orphan_swept", document_id=str(row["id"]))
        return len(rows)
