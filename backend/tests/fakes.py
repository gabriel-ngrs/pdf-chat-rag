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

Os dois dublês do chat seguem a mesma disciplina, com um acréscimo:

* `FakeChatClient` guarda **o prompt que recebeu** em cada método. É o que
  permite asserir sobre o que o turno entregou ao provedor — a ordem das partes
  do prompt (NFR-8) e o fato de a recusa nem chegar a chamá-lo (AC-8) — sem
  depender do texto que um modelo real devolveria, que não é determinístico.
* `FakeConversationRepository` guarda **o embedding que chegou ao
  `search_chunks`**. A query condensada não é observável na resposta; o vetor
  que foi buscar é, e como o `FakeEmbeddingClient` é determinístico, comparar o
  vetor com `deterministic_vector(query_esperada)` prova qual texto foi ao
  retrieval (AC-5).

Os dois aceitam um `journal` compartilhado porque a garantia de FR-9 — a
pergunta é gravada **antes** de qualquer chamada ao provedor — atravessa dois
colaboradores, e uma linha do tempo única é a única forma de asseri-la sem
inspecionar o código de produção.
"""

import asyncio
import hashlib
import itertools
import math
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from google.genai import types

from app.adapters.repository import ConversationRecord, DocumentRecord
from app.core.models import (
    Chunk,
    Citation,
    DocumentStatus,
    Message,
    MessageRole,
    RetrievedChunk,
)

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


# ─── Dublês do chat ──────────────────────────────────────────────────────────

DEFAULT_ANSWER_PIECES: tuple[str, ...] = (
    "A YAITEC ",
    "atende empresas ",
    "com projetos de software (página 2).",
)

DEFAULT_CONDENSED_QUERY = "quais servicos a YAITEC oferece para empresas?"


def matches_embedding(embedding: list[float], text: str, dim: int = DEFAULT_DIM) -> bool:
    """Diz se o vetor que chegou ao retrieval é o vetor do texto dado.

    A ponte entre "qual query foi buscar" e "qual vetor foi buscado" é o
    determinismo do `FakeEmbeddingClient`: o mesmo texto sempre produz o mesmo
    vetor, então comparar vetores é comparar textos — sem que o teste precise
    inspecionar a chamada intermediária.
    """
    return embedding == deterministic_vector(text, dim)


class FakeChatClient:
    """Implementa `ChatClient` sem rede, com os caminhos que só aparecem sob falha.

    Quatro modos, todos configuráveis pelo construtor, porque são exatamente os
    quatro que o uso normal nunca exercita:

    * `stream_error` com `error_after=0` — o provedor recusa **na abertura** do
      stream, antes de qualquer token. É o caso comum do `429` do free tier.
    * `stream_error` com `error_after=n` — o provedor morre depois de `n`
      pedaços já entregues, que é a metade `mid_stream` de FR-11.
    * `generate_error` / `generate_delay` — a condensação falha ou estoura o
      prazo. O prazo é honrado com o mesmo `asyncio.wait_for` do adapter real,
      para que o `TimeoutError` venha de um timeout de verdade e não de uma
      exceção escolhida à mão (AC-5).
    * `echo_prompt` — a resposta é o próprio prompt. É o que torna a ordem das
      partes do prompt observável de fora, pelo stream (AC-27).

    `emitted` e `closed` existem para a desconexão (AC-13): o primeiro mostra
    que o consumo parou antes do fim, e o segundo que o iterador do provedor foi
    fechado — o `finally` do gerador só roda no `aclose()`.
    """

    def __init__(
        self,
        *,
        pieces: Sequence[str] = DEFAULT_ANSWER_PIECES,
        condensed: str = DEFAULT_CONDENSED_QUERY,
        stream_error: Exception | None = None,
        error_after: int = 0,
        generate_error: Exception | None = None,
        generate_delay: float | None = None,
        echo_prompt: bool = False,
        journal: list[str] | None = None,
    ) -> None:
        self.pieces = list(pieces)
        self.condensed = condensed
        self.stream_error = stream_error
        self.error_after = error_after
        self.generate_error = generate_error
        self.generate_delay = generate_delay
        self.echo_prompt = echo_prompt
        self.journal = journal if journal is not None else []
        self.stream_prompts: list[str] = []
        self.generate_prompts: list[str] = []
        self.emitted: list[str] = []
        self.closed = False

    @property
    def stream_calls(self) -> int:
        """Quantas vezes o turno pediu geração — zero é o que a recusa promete."""
        return len(self.stream_prompts)

    async def generate(self, prompt: str, *, timeout: float) -> str:
        self.generate_prompts.append(prompt)
        self.journal.append("generate")
        if self.generate_error is not None:
            raise self.generate_error
        if self.generate_delay is not None:
            await asyncio.wait_for(asyncio.sleep(self.generate_delay), timeout)
        return self.condensed

    async def stream_answer(self, prompt: str) -> AsyncIterator[str]:
        self.stream_prompts.append(prompt)
        self.journal.append("stream_answer")
        pieces = [prompt] if self.echo_prompt else self.pieces
        try:
            for position, piece in enumerate(pieces):
                self._fail_if_due(position)
                self.emitted.append(piece)
                yield piece
            self._fail_if_due(len(pieces))
        finally:
            self.closed = True

    def _fail_if_due(self, emitted: int) -> None:
        """Levanta a falha injetada quando ela é devida depois de `emitted` pedaços."""
        if self.stream_error is not None and emitted >= self.error_after:
            raise self.stream_error


@dataclass(frozen=True, slots=True)
class SearchCall:
    """Uma chamada ao `search_chunks`, como ela chegou ao repositório."""

    document_id: UUID
    embedding: list[float]
    limit: int


class FakeConversationRepository:
    """Implementa `ConversationRepository` sobre listas em memória.

    Os ids de mensagem são inteiros crescentes, como o `bigserial` da tabela: o
    evento `done` devolve esse id ao cliente, e um dublê que devolvesse sempre o
    mesmo esconderia a troca de uma mensagem por outra.

    `chunks` e seus scores são configuráveis porque é o score que decide entre
    responder e recusar — é o único parâmetro que separa o caminho fundamentado
    do caminho de recusa (AC-8).
    """

    def __init__(
        self,
        *,
        chunks: Sequence[RetrievedChunk] = (),
        journal: list[str] | None = None,
    ) -> None:
        self.conversations: dict[UUID, ConversationRecord] = {}
        self.messages: dict[UUID, list[Message]] = {}
        self.chunks = list(chunks)
        self.searches: list[SearchCall] = []
        self.operations: list[str] = []
        self.journal = journal if journal is not None else []
        self.fail_on: str | None = None
        self.failure: Exception | None = None
        self._ids = itertools.count(1)

    async def _enter(self, operation: str) -> None:
        """Cede o loop, registra a chamada e dispara a falha injetada, se houver."""
        await asyncio.sleep(0)
        self.operations.append(operation)
        self.journal.append(operation)
        if self.fail_on == operation and self.failure is not None:
            raise self.failure

    async def create_conversation(self, document_id: UUID, session_id: str | None) -> UUID:
        await self._enter("create_conversation")
        conversation_id = uuid4()
        self.conversations[conversation_id] = ConversationRecord(
            id=conversation_id,
            document_id=document_id,
            session_id=session_id,
            created_at=datetime.now(UTC),
        )
        self.messages[conversation_id] = []
        return conversation_id

    async def get_conversation(self, conversation_id: UUID) -> ConversationRecord | None:
        await self._enter("get_conversation")
        return self.conversations.get(conversation_id)

    async def add_message(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        citations: tuple[Citation, ...] = (),
        truncated: bool = False,
    ) -> Message:
        await self._enter("add_message")
        message = Message(
            id=next(self._ids),
            role=role,
            content=content,
            citations=tuple(citations),
            truncated=truncated,
            created_at=datetime.now(UTC),
        )
        self.messages.setdefault(conversation_id, []).append(message)
        return message

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        await self._enter("list_messages")
        return list(self.messages.get(conversation_id, []))

    async def search_chunks(
        self, document_id: UUID, embedding: list[float], limit: int
    ) -> list[RetrievedChunk]:
        """Devolve os `limit` chunks configurados, do mais similar para o menos.

        A ordenação é refeita aqui porque é o que o `ORDER BY` do SQL real faz —
        um dublê que devolvesse na ordem em que o teste montou a lista deixaria
        passar um `take_top_k` que dependesse da ordem de chegada.
        """
        await self._enter("search_chunks")
        self.searches.append(SearchCall(document_id, list(embedding), limit))
        ranked = sorted(self.chunks, key=lambda chunk: chunk.score, reverse=True)
        return ranked[:limit]

    def contents_of(self, conversation_id: UUID) -> list[tuple[str, str]]:
        """Papel e texto de cada mensagem gravada, na ordem — o histórico cru."""
        return [
            (message.role.value, message.content)
            for message in self.messages.get(conversation_id, [])
        ]
