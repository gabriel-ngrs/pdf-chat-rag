"""Persistência de documentos e chunks.

Todo SQL é escrito à mão e parametrizado — não existe ORM nem query builder no
projeto, e nenhuma string de SQL é montada por concatenação com entrada externa.

O protocolo `DocumentRepository` existe para que a suíte offline substitua o
banco por um dublê em memória: é ele que torna `make check` executável na
máquina de quem clona o projeto, sem Postgres no ar.
"""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.adapters.db import Database
from app.core.models import Chunk, DocumentStatus

_CREATE_SQL = """
    INSERT INTO documents (filename, content_hash, status, session_id)
         VALUES ($1, $2, $3, $4)
      RETURNING id
"""

_GET_SQL = """
    SELECT id, filename, status, error_message, page_count,
           chunks_total, chunks_processed
      FROM documents
     WHERE id = $1
"""

_FIND_BY_HASH_SQL = """
    SELECT id, filename, status, error_message, page_count,
           chunks_total, chunks_processed
      FROM documents
     WHERE session_id IS NOT DISTINCT FROM $1
       AND content_hash = $2
"""

_SET_STATUS_SQL = """
    UPDATE documents
       SET status = $2,
           error_message = $3
     WHERE id = $1
"""

_SET_TOTALS_SQL = """
    UPDATE documents
       SET page_count = $2,
           chunks_total = $3
     WHERE id = $1
"""

_UPDATE_PROGRESS_SQL = """
    UPDATE documents
       SET chunks_processed = $2
     WHERE id = $1
"""

_INSERT_CHUNK_SQL = """
    INSERT INTO chunks (document_id, chunk_index, page_number, content, embedding)
         VALUES ($1, $2, $3, $4, $5::vector)
"""

_RESET_FOR_RETRY_SQL = """
    UPDATE documents
       SET status = $2,
           error_message = NULL,
           page_count = NULL,
           chunks_total = NULL,
           chunks_processed = 0
     WHERE id = $1
"""

_DELETE_CHUNKS_SQL = "DELETE FROM chunks WHERE document_id = $1"


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """Estado de um documento como a API o publica."""

    id: UUID
    filename: str
    status: DocumentStatus
    error_message: str | None
    page_count: int | None
    chunks_total: int | None
    chunks_processed: int


class DocumentRepository(Protocol):
    """O que o pipeline de ingestão e as rotas precisam do armazenamento."""

    async def create(self, filename: str, content_hash: str, session_id: str | None) -> UUID: ...

    async def get(self, document_id: UUID) -> DocumentRecord | None: ...

    async def find_by_hash(
        self, session_id: str | None, content_hash: str
    ) -> DocumentRecord | None: ...

    async def set_status(
        self, document_id: UUID, status: DocumentStatus, error_message: str | None = None
    ) -> None: ...

    async def set_totals(self, document_id: UUID, page_count: int, chunks_total: int) -> None: ...

    async def update_progress(self, document_id: UUID, chunks_processed: int) -> None: ...

    async def insert_chunks(
        self, document_id: UUID, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None: ...

    async def reset_for_retry(self, document_id: UUID) -> None: ...

    async def sweep_orphans(self) -> int: ...


def vector_literal(values: list[float]) -> str:
    """Formata o vetor no literal que o pgvector aceita.

    O valor continua entrando como parâmetro (`$5::vector`); o que esta função
    produz é o conteúdo do parâmetro, nunca um pedaço da query.
    """
    return "[" + ",".join(repr(float(value)) for value in values) + "]"


class PostgresDocumentRepository:
    """Implementação sobre o pool asyncpg criado no lifespan."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self, filename: str, content_hash: str, session_id: str | None) -> UUID:
        """Grava o documento em `pending` e devolve o id gerado pelo banco."""
        document_id = await self._database.pool.fetchval(
            _CREATE_SQL, filename, content_hash, DocumentStatus.PENDING.value, session_id
        )
        return UUID(str(document_id))

    async def get(self, document_id: UUID) -> DocumentRecord | None:
        """Lê o estado de um documento, ou `None` se ele não existir.

        Devolver `None` em vez de levantar mantém a decisão de virar `404` na
        rota, que é quem conhece o envelope de erro.
        """
        row = await self._database.pool.fetchrow(_GET_SQL, document_id)
        return _to_record(row)

    async def find_by_hash(
        self, session_id: str | None, content_hash: str
    ) -> DocumentRecord | None:
        """Procura documento idêntico já enviado na mesma sessão.

        `IS NOT DISTINCT FROM` em vez de `=` porque `session_id` pode ser nulo, e
        `NULL = NULL` seria falso — sem isso, quem não manda o header reprocessa
        o mesmo PDF a cada envio, queimando quota à toa.
        """
        row = await self._database.pool.fetchrow(_FIND_BY_HASH_SQL, session_id, content_hash)
        return _to_record(row)

    async def set_status(
        self, document_id: UUID, status: DocumentStatus, error_message: str | None = None
    ) -> None:
        """Move o documento de estado, gravando junto a mensagem ao usuário.

        `error_message` é escrita sempre, inclusive como `NULL`: assim uma
        transição de saída de `failed` não deixa para trás o texto do erro
        anterior, que a tela exibiria como se ainda valesse.
        """
        await self._database.pool.execute(_SET_STATUS_SQL, document_id, status.value, error_message)

    async def set_totals(self, document_id: UUID, page_count: int, chunks_total: int) -> None:
        """Publica os totais assim que o chunking termina.

        Enquanto `chunks_total` é nulo a tela mostra progresso indeterminado —
        é a ausência deste valor que a distingue de "processou zero chunks".
        """
        await self._database.pool.execute(_SET_TOTALS_SQL, document_id, page_count, chunks_total)

    async def update_progress(self, document_id: UUID, chunks_processed: int) -> None:
        """Grava quantos chunks já foram embedados.

        Chamada a cada lote, e não ao final, porque a ingestão passa de meio
        minuto no teto da spec e uma barra parada em zero parece travamento.
        """
        await self._database.pool.execute(_UPDATE_PROGRESS_SQL, document_id, chunks_processed)

    async def insert_chunks(
        self, document_id: UUID, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        """Grava os chunks numa única viagem, dentro de uma transação.

        Em lote e não um por vez porque são dezenas de linhas por documento, e
        cada ida ao banco custa mais que a inserção em si.
        """
        rows = [
            (
                document_id,
                chunk.chunk_index,
                chunk.page_number,
                chunk.content,
                vector_literal(embedding),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        async with self._database.pool.acquire() as connection, connection.transaction():
            await connection.executemany(_INSERT_CHUNK_SQL, rows)

    async def reset_for_retry(self, document_id: UUID) -> None:
        """Devolve um documento que falhou ao estado inicial, para reprocessar.

        Reaproveita a linha existente em vez de criar outra porque
        `UNIQUE (session_id, content_hash)` impediria a segunda — e porque o
        usuário espera reenviar "o mesmo documento", não ganhar um id novo.

        Os chunks são apagados junto: se a falha aconteceu depois da inserção,
        reprocessar sem limpar duplicaria o conteúdo indexado.
        """
        async with self._database.pool.acquire() as connection, connection.transaction():
            await connection.execute(_DELETE_CHUNKS_SQL, document_id)
            await connection.execute(
                _RESET_FOR_RETRY_SQL, document_id, DocumentStatus.PENDING.value
            )

    async def sweep_orphans(self) -> int:
        """Delega ao `Database`, que já implementa a varredura usada no startup."""
        return await self._database.sweep_orphans()


def _to_record(row: Any) -> DocumentRecord | None:
    if row is None:
        return None
    return DocumentRecord(
        id=UUID(str(row["id"])),
        filename=row["filename"],
        status=DocumentStatus(row["status"]),
        error_message=row["error_message"],
        page_count=row["page_count"],
        chunks_total=row["chunks_total"],
        chunks_processed=row["chunks_processed"],
    )
