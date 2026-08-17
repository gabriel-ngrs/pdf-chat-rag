"""Rotas de documento: recebimento do upload e consulta de estado.

A divisão de responsabilidade com `app.ingestion` é a decisão central da fase:
aqui ficam só as validações baratas, que cabem numa requisição. Tudo que exige
abrir o PDF acontece no background, porque um documento no teto da spec leva
dezenas de segundos só embedando e nenhum request sobrevive a isso.
"""

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, status
from starlette.datastructures import UploadFile

from app.adapters.gemini import EmbeddingClient
from app.adapters.repository import DocumentRepository
from app.api.schemas import DocumentResponse, UploadAcceptedResponse
from app.config import Settings, get_settings
from app.core.models import DocumentStatus
from app.errors import FileTooLargeError, InvalidFileError, NotFoundError
from app.ingestion import run_ingestion
from app.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter()


def get_repository(request: Request) -> DocumentRepository:
    """Devolve o repositório montado no lifespan.

    Dependência, e não import de módulo, para que a suíte offline injete o
    dublê em memória sem precisar de Postgres no ar.
    """
    repository: DocumentRepository | None = getattr(request.app.state, "repository", None)
    if repository is None:
        raise RuntimeError("O repositório não foi inicializado.")
    return repository


def get_embedder(request: Request) -> EmbeddingClient:
    """Devolve o cliente de embeddings montado no lifespan."""
    embedder: EmbeddingClient | None = getattr(request.app.state, "embedder", None)
    if embedder is None:
        raise RuntimeError("O cliente de embeddings não foi inicializado.")
    return embedder


RepositoryDep = Annotated[DocumentRepository, Depends(get_repository)]
EmbedderDep = Annotated[EmbeddingClient, Depends(get_embedder)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

PDF_SIGNATURE = b"%PDF"
_READ_CHUNK_BYTES = 64 * 1024

MISSING_FILE_MESSAGE = "Envie um arquivo PDF no campo 'file'."
NOT_PDF_MESSAGE = "O arquivo enviado não é um PDF. Envie um documento com extensão .pdf válida."
NOT_FOUND_MESSAGE = "Documento não encontrado."


def _too_large_message(limit_mb: int) -> str:
    return f"O arquivo excede o limite de {limit_mb} MB."


def _reject_by_declared_size(request: Request, limit_bytes: int, limit_mb: int) -> None:
    """Recusa pelo `Content-Length`, antes de ler um byte do corpo.

    Ler para depois medir não protege memória nenhuma: no momento em que o
    arquivo inteiro está na mão, o custo já foi pago.
    """
    declared = request.headers.get("content-length")
    if declared is None:
        return
    try:
        size = int(declared)
    except ValueError as erro:
        raise InvalidFileError(MISSING_FILE_MESSAGE) from erro
    if size > limit_bytes:
        raise FileTooLargeError(_too_large_message(limit_mb))


async def _read_capped(upload: UploadFile, limit_bytes: int, limit_mb: int) -> bytes:
    """Lê o arquivo em pedaços, cortando com rigor no limite.

    O corte é duro porque o `Content-Length` é informado pelo cliente e pode
    mentir; sem este segundo controle, o limite seria uma sugestão.
    """
    parts: list[bytes] = []
    total = 0
    while piece := await upload.read(_READ_CHUNK_BYTES):
        total += len(piece)
        if total > limit_bytes:
            raise FileTooLargeError(_too_large_message(limit_mb))
        parts.append(piece)
    return b"".join(parts)


@router.post(
    "/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAcceptedResponse,
)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    repository: RepositoryDep,
    embedder: EmbedderDep,
    settings: SettingsDep,
    session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> UploadAcceptedResponse:
    """Aceita o PDF, responde `202` e deixa o processamento para o background.

    O corpo é lido como formulário cru em vez de por `UploadFile` declarado na
    assinatura porque o limite de tamanho precisa ser conferido **antes** de o
    framework consumir o corpo inteiro.
    """
    _reject_by_declared_size(request, settings.max_upload_bytes, settings.max_upload_mb)

    async with request.form() as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise InvalidFileError(MISSING_FILE_MESSAGE)
        data = await _read_capped(upload, settings.max_upload_bytes, settings.max_upload_mb)
        filename = upload.filename or "documento.pdf"

    if not data.startswith(PDF_SIGNATURE):
        raise InvalidFileError(NOT_PDF_MESSAGE)

    content_hash = hashlib.sha256(data).hexdigest()

    existing = await repository.find_by_hash(session_id, content_hash)
    if existing is not None:
        logger.info("document.duplicate", document_id=str(existing.id), content_hash=content_hash)
        return UploadAcceptedResponse(id=existing.id, status=existing.status)

    document_id = await repository.create(filename, content_hash, session_id)
    logger.info(
        "document.received",
        document_id=str(document_id),
        filename=filename,
        size_bytes=len(data),
    )

    # O request_id é capturado agora, no contexto da requisição: dentro da task
    # ele já não existe, e sem ele a ingestão não aparece no mesmo `grep`.
    background_tasks.add_task(
        run_ingestion,
        document_id,
        data,
        getattr(request.state, "request_id", ""),
        repository,
        embedder,
        settings,
    )
    return UploadAcceptedResponse(id=document_id, status=DocumentStatus.PENDING)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def read_document(document_id: UUID, repository: RepositoryDep) -> DocumentResponse:
    """Devolve o estado do documento, incluindo o progresso do processamento."""
    record = await repository.get(document_id)
    if record is None:
        raise NotFoundError(NOT_FOUND_MESSAGE)
    return DocumentResponse(
        id=record.id,
        filename=record.filename,
        status=record.status,
        page_count=record.page_count,
        chunks_total=record.chunks_total,
        chunks_processed=record.chunks_processed,
        error_message=record.error_message,
    )
