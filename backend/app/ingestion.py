"""Pipeline de ingestão: de bytes de PDF a chunks embedados e persistidos.

É a máquina de estados do documento. A regra que organiza o módulo inteiro:
**nenhum caminho pode deixar o documento em `processing`** — se deixasse, a tela
mostraria barra eterna e o usuário não teria como saber o que aconteceu.

A separação entre o que é validado na requisição e o que é validado aqui é
deliberada: tudo que exige parse do PDF é caro demais para segurar um request.
"""

import asyncio
import time
from collections.abc import Iterator, Sequence
from uuid import UUID

from app.adapters.gemini import EmbeddingClient
from app.adapters.pdf import NO_TEXT_MESSAGE, extract_pages
from app.adapters.repository import DocumentRepository
from app.config import Settings
from app.core.chunking import chunk_pages
from app.core.models import Chunk, DocumentStatus
from app.errors import AppError, InternalError, PdfWithoutTextError
from app.logging_setup import bind_document_id, bind_request_id, clear_request_context, get_logger

logger = get_logger(__name__)

UNEXPECTED_MESSAGE = (
    "Não foi possível processar o documento por uma falha interna. Tente enviar de novo."
)

# NFR-8: uma ingestão por vez. Duas em paralelo cairiam ambas em 429, porque o
# limite de tokens por minuto do free tier é do projeto, não da requisição.
_pipeline_lock = asyncio.Semaphore(1)


async def run_ingestion(
    document_id: UUID,
    data: bytes,
    request_id: str,
    repository: DocumentRepository,
    embedder: EmbeddingClient,
    settings: Settings,
) -> None:
    """Processa um documento já persistido em `pending` até `ready` ou `failed`.

    Recebe `bytes`, e não o `UploadFile`, para não depender do ciclo de vida do
    arquivo temporário da requisição, que termina antes desta rotina.

    O `request_id` chega por parâmetro porque a task roda fora do contexto da
    requisição que a agendou: reamarrá-lo aqui é o que faz a ingestão inteira
    aparecer num único `grep` no log.

    O `total_duration_ms` de `document.ready` conta **desde o início da task,
    incluindo a espera pelo semáforo** — e não só o processamento. É a leitura
    que responde "quanto o usuário esperou", que é a pergunta que a métrica
    serve para responder; as durações por etapa ficam nos eventos de etapa.
    """
    bind_request_id(request_id)
    bind_document_id(str(document_id))
    started = time.perf_counter()
    try:
        async with _pipeline_lock:
            chunk_count = await _process(document_id, data, repository, embedder, settings)
        logger.info(
            "document.ready",
            chunk_count=chunk_count,
            total_duration_ms=_elapsed_ms(started),
        )
    except AppError as error:
        await _fail(repository, document_id, error.code, error.message)
    except Exception:
        # Sem `raise`: a task roda depois da resposta, então propagar só produziria
        # um traceback órfão e deixaria o documento preso em `processing`.
        logger.exception("document.unexpected_error")
        await _fail(repository, document_id, InternalError.code, UNEXPECTED_MESSAGE)
    finally:
        clear_request_context()


async def _process(
    document_id: UUID,
    data: bytes,
    repository: DocumentRepository,
    embedder: EmbeddingClient,
    settings: Settings,
) -> int:
    """Executa as etapas da ingestão e devolve quantos chunks foram gravados."""
    await repository.set_status(document_id, DocumentStatus.PROCESSING)

    started = time.perf_counter()
    # `pypdf` é síncrono e CPU-bound: fora da thread ele travaria o event loop
    # inteiro por dezenas de segundos, e a API pararia de responder.
    pages = await asyncio.to_thread(
        extract_pages,
        data,
        max_pages=settings.max_pdf_pages,
        max_chars=settings.max_extracted_chars,
    )
    char_count = sum(len(page.text) for page in pages)
    logger.info(
        "document.extracted",
        page_count=len(pages),
        char_count=char_count,
        duration_ms=_elapsed_ms(started),
    )

    started = time.perf_counter()
    chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
    logger.info("document.chunked", chunk_count=len(chunks), duration_ms=_elapsed_ms(started))

    # Defesa em profundidade sobre o guarda de `extract_pages`: um documento sem
    # chunk nenhum não pode terminar `ready`. Se terminasse, a tela diria
    # "pronto" e toda pergunta receberia "não encontrei isso no documento" — o
    # diagnóstico errado, porque o problema é o documento e não a pergunta.
    if not chunks:
        raise PdfWithoutTextError(NO_TEXT_MESSAGE)

    await repository.set_totals(document_id, page_count=len(pages), chunks_total=len(chunks))

    embeddings = await _embed_in_batches(chunks, embedder, repository, document_id, settings)

    await repository.insert_chunks(document_id, chunks, embeddings)
    await repository.set_status(document_id, DocumentStatus.READY)
    return len(chunks)


async def _embed_in_batches(
    chunks: list[Chunk],
    embedder: EmbeddingClient,
    repository: DocumentRepository,
    document_id: UUID,
    settings: Settings,
) -> list[list[float]]:
    """Embeda os chunks em lotes, publicando o progresso após cada um.

    O progresso é gravado por lote, e não ao final, porque a ingestão de um
    documento no teto da spec passa de meio minuto: sem isso a tela ficaria
    parada em zero e pareceria travada (NFR-1).
    """
    embeddings: list[list[float]] = []
    for batch in _batched(chunks, settings.embedding_batch_size):
        texts = [chunk.content for chunk in batch]
        # Síncrono no SDK do provedor: também vai para uma thread.
        embeddings.extend(await asyncio.to_thread(embedder.embed_documents, texts))
        await repository.update_progress(document_id, len(embeddings))
    return embeddings


def _batched(chunks: Sequence[Chunk], size: int) -> Iterator[list[Chunk]]:
    step = max(1, size)
    for start in range(0, len(chunks), step):
        yield list(chunks[start : start + step])


async def _fail(
    repository: DocumentRepository, document_id: UUID, code: str, message: str
) -> None:
    """Encerra o documento em `failed`, com a mensagem que a tela vai exibir.

    É o único ponto de saída por erro do pipeline, o que garante que nenhum
    caminho deixe o documento parado em `processing`.
    """
    logger.error("document.failed", code=code, message=message)
    try:
        await repository.set_status(document_id, DocumentStatus.FAILED, message)
    except Exception:
        # Se nem o banco responde, o documento fica órfão e a varredura do
        # próximo startup o resolve — mas o motivo precisa aparecer no log.
        logger.exception("document.failed_not_persisted")


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
