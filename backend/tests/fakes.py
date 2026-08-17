"""Dublês em memória dos protocolos de I/O que a ingestão consome.

Existem para que a suíte offline exercite o pipeline inteiro sem Postgres, sem
rede e sem `GEMINI_API_KEY` — que é a condição do gate (AC-25). São eles também
que provam que os protocolos de `adapters/` não são decorativos: se o pipeline
dependesse de `asyncpg` ou do SDK do provedor, nenhum destes dublês serviria.

Duas escolhas merecem registro:

* `FakeRepository` **registra a ordem de todas as chamadas** e cede o controle do
  event loop (`await asyncio.sleep(0)`) antes de cada uma. O primeiro é o que
  torna a monotonicidade do progresso e a serialização do pipeline verificáveis
  por asserção; o segundo é o que torna a intercalação de duas ingestões
  *detectável* — sem ponto de troca de contexto, um teste de concorrência
  passaria mesmo que o semáforo fosse removido.
* `FakeEmbeddingClient` devolve vetor derivado do hash do texto e já normalizado
  em L2, como o adapter real garante. Determinístico porque o mesmo texto
  precisa produzir o mesmo vetor entre execuções, e normalizado porque um dublê
  que não respeitasse essa garantia esconderia regressões na distância de
  cosseno.
"""

import asyncio
import hashlib
import math
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from google.genai import types

from app.adapters.repository import DocumentRecord
from app.core.models import Chunk, DocumentStatus

# Pequena de propósito na suíte offline: o valor de produção é 768 e nada no
# pipeline depende do número, então vetor curto só torna o teste mais barato.
DEFAULT_DIM = 8

_BYTES_PER_VALUE = 2
_DIGEST_BYTES = 32
_MAX_UINT16 = 65535.0


def deterministic_vector(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """Devolve um vetor reprodutível para o texto, com norma L2 igual a 1.

    O material vem de blocos de SHA-256 numerados, e não do digest repetido, para
    que dois textos distintos não compartilhem padrão em dimensões diferentes —
    vetores quase paralelos por construção tornariam qualquer teste de
    similaridade vacuamente verdadeiro.
    """
    blocks = (dim * _BYTES_PER_VALUE + _DIGEST_BYTES - 1) // _DIGEST_BYTES
    material = b"".join(
        hashlib.sha256(text.encode("utf-8") + index.to_bytes(4, "big")).digest()
        for index in range(blocks)
    )
    raw = [
        int.from_bytes(material[start : start + _BYTES_PER_VALUE], "big") / _MAX_UINT16 - 0.5
        for start in range(0, dim * _BYTES_PER_VALUE, _BYTES_PER_VALUE)
    ]
    norm = math.sqrt(sum(value * value for value in raw))
    if norm == 0.0:
        raise ValueError("O vetor determinístico saiu nulo; escolha outro texto.")
    return [value / norm for value in raw]


class FakeEmbeddingClient:
    """Implementa `EmbeddingClient` sem rede e sem chave de API.

    `error` injeta falha permanente do provedor: é assim que o teste de AC-13
    exercita o caminho de erro sem depender de um `429` real.
    """

    def __init__(self, *, dim: int = DEFAULT_DIM, error: Exception | None = None) -> None:
        self.dim = dim
        self.error = error
        self.batches: list[list[str]] = []
        self.query_calls: list[str] = []

    @property
    def embedded_texts(self) -> list[str]:
        """Todos os textos já embedados, na ordem em que chegaram."""
        return [text for batch in self.batches for text in batch]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        if self.error is not None:
            raise self.error
        return [deterministic_vector(text, self.dim) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        if self.error is not None:
            raise self.error
        return deterministic_vector(text, self.dim)


class FakeRepository:
    """Implementa `DocumentRepository` sobre dicionários em memória.

    Além de guardar o estado, mantém três diários que os testes leem: a ordem de
    todas as operações (`operations`), as transições de estado (`status_calls`) e
    cada publicação de progresso (`progress_calls`).
    """

    def __init__(self) -> None:
        self.documents: dict[UUID, DocumentRecord] = {}
        self.chunks: dict[UUID, list[tuple[Chunk, list[float]]]] = {}
        self.hashes: dict[tuple[str | None, str], UUID] = {}
        self.operations: list[tuple[str, UUID]] = []
        self.status_calls: list[tuple[UUID, DocumentStatus]] = []
        self.progress_calls: list[tuple[UUID, int]] = []
        self.retries: list[UUID] = []
        self.fail_on: str | None = None
        self.failure: Exception | None = None

    async def _enter(self, operation: str, document_id: UUID) -> None:
        """Cede o loop, registra a chamada e dispara a falha injetada, se houver.

        O `sleep(0)` é o que dá ao event loop a chance de trocar de tarefa dentro
        do pipeline: sem ele, duas ingestões concorrentes rodariam em sequência
        por acidente e o teste do semáforo (AC-28) não provaria nada.
        """
        await asyncio.sleep(0)
        self.operations.append((operation, document_id))
        if self.fail_on == operation and self.failure is not None:
            raise self.failure

    async def create(self, filename: str, content_hash: str, session_id: str | None) -> UUID:
        document_id = uuid4()
        await self._enter("create", document_id)
        self.documents[document_id] = DocumentRecord(
            id=document_id,
            filename=filename,
            status=DocumentStatus.PENDING,
            error_message=None,
            page_count=None,
            chunks_total=None,
            chunks_processed=0,
        )
        self.hashes[(session_id, content_hash)] = document_id
        return document_id

    async def get(self, document_id: UUID) -> DocumentRecord | None:
        await self._enter("get", document_id)
        return self.documents.get(document_id)

    async def find_by_hash(
        self, session_id: str | None, content_hash: str
    ) -> DocumentRecord | None:
        """Espelha o `IS NOT DISTINCT FROM` do SQL: `None` é uma sessão como outra."""
        document_id = self.hashes.get((session_id, content_hash))
        if document_id is None:
            return None
        return self.documents.get(document_id)

    async def set_status(
        self, document_id: UUID, status: DocumentStatus, error_message: str | None = None
    ) -> None:
        await self._enter("set_status", document_id)
        self.status_calls.append((document_id, status))
        self.documents[document_id] = replace(
            self.documents[document_id], status=status, error_message=error_message
        )

    async def set_totals(self, document_id: UUID, page_count: int, chunks_total: int) -> None:
        await self._enter("set_totals", document_id)
        self.documents[document_id] = replace(
            self.documents[document_id], page_count=page_count, chunks_total=chunks_total
        )

    async def update_progress(self, document_id: UUID, chunks_processed: int) -> None:
        await self._enter("update_progress", document_id)
        self.progress_calls.append((document_id, chunks_processed))
        self.documents[document_id] = replace(
            self.documents[document_id], chunks_processed=chunks_processed
        )

    async def insert_chunks(
        self, document_id: UUID, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        await self._enter("insert_chunks", document_id)
        self.chunks[document_id] = list(zip(chunks, embeddings, strict=True))

    async def reset_for_retry(self, document_id: UUID) -> None:
        await self._enter("reset_for_retry", document_id)
        self.retries.append(document_id)
        self.chunks.pop(document_id, None)
        self.documents[document_id] = replace(
            self.documents[document_id],
            status=DocumentStatus.PENDING,
            error_message=None,
            page_count=None,
            chunks_total=None,
            chunks_processed=0,
        )

    async def sweep_orphans(self) -> int:
        pending = [
            record
            for record in self.documents.values()
            if record.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING)
        ]
        for record in pending:
            self.documents[record.id] = replace(record, status=DocumentStatus.FAILED)
        return len(pending)

    def progress_of(self, document_id: UUID) -> list[int]:
        """Só os valores de progresso do documento dado, na ordem publicada."""
        return [count for target, count in self.progress_calls if target == document_id]

    def statuses_of(self, document_id: UUID) -> list[DocumentStatus]:
        """Só as transições de estado do documento dado, na ordem aplicada."""
        return [status for target, status in self.status_calls if target == document_id]


class StubGenaiModels:
    """A fatia `client.models` do SDK do provedor, sem rede.

    Serve aos testes de log, que precisam do adapter **real** para ver o evento
    `embedding.batch` — trocar o adapter inteiro por um dublê apagaria justamente
    o evento que o AC-18 exige.
    """

    def __init__(self, failures: list[Exception | None] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._failures = list(failures or [])

    def embed_content(
        self, *, model: str, contents: Any, config: types.EmbedContentConfig
    ) -> types.EmbedContentResponse:
        texts = list(contents)
        self.calls.append(texts)
        if self._failures:
            failure = self._failures.pop(0)
            if failure is not None:
                raise failure
        return types.EmbedContentResponse(
            embeddings=[
                types.ContentEmbedding(values=deterministic_vector(str(text)))
                for text in texts
            ]
        )


class StubGenaiClient:
    """Cliente do SDK reduzido ao único atributo que o adapter alcança."""

    def __init__(self, models: StubGenaiModels) -> None:
        self.models = models
