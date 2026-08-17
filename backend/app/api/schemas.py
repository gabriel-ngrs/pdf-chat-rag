"""Schemas de resposta da API.

São a fonte que o frontend espelha em `types.ts`. Mudar um campo aqui é mudança
quebradora de contrato entre os dois tracks.
"""

from uuid import UUID

from pydantic import BaseModel

from app.core.models import DocumentStatus


class HealthResponse(BaseModel):
    """Resultado da sonda de saúde, incluindo a conectividade com o banco."""

    status: str
    database: str


class ConfigResponse(BaseModel):
    """Limites vigentes no servidor.

    Existem para que o cliente valide contra os mesmos números que o servidor
    aplica, em vez de duplicá-los numa constante que envelhece.
    """

    max_upload_mb: int
    max_pdf_pages: int
    max_extracted_chars: int


class UploadAcceptedResponse(BaseModel):
    """Resposta do `202`: o documento foi aceito e o processamento vai começar."""

    id: UUID
    status: DocumentStatus


class DocumentResponse(BaseModel):
    """Estado do documento durante e depois do processamento.

    `chunks_total` é nulo até o chunking terminar — a UI usa essa ausência para
    mostrar progresso indeterminado em vez de inventar um número.
    """

    id: UUID
    filename: str
    status: DocumentStatus
    page_count: int | None
    chunks_total: int | None
    chunks_processed: int
    error_message: str | None
