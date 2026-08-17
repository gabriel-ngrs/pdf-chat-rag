"""Schemas de resposta da API.

São a fonte que o frontend espelha em `types.ts`. Mudar um campo aqui é mudança
quebradora de contrato entre os dois tracks.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from app.core.models import DocumentStatus, MessageRole


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


class ConversationCreateRequest(BaseModel):
    """Corpo de `POST /api/conversations`: a que documento a conversa se prende."""

    document_id: UUID


class ConversationResponse(BaseModel):
    """Resposta do `201`: o id que o cliente guarda para o resto da conversa."""

    id: UUID


# A pergunta é validada no servidor porque o cliente não é a fronteira de
# confiança (rule `security`). O piso de um caractere **depois** de podar os
# espaços recusa a pergunta que é só espaço em branco, que passaria por um
# `min_length` cru; o teto existe porque uma pergunta gigante não é pergunta —
# é um jeito de fazer o servidor pagar tokenização por conteúdo que o retrieval
# não usaria de qualquer forma.
MAX_QUESTION_LENGTH = 2000

QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH)
]


class QuestionRequest(BaseModel):
    """Corpo de `POST /api/conversations/{id}/messages`."""

    question: QuestionText


class CitationResponse(BaseModel):
    """Uma citação como a API a publica, espelhando `core.models.Citation`.

    O `snippet` já vem recortado do servidor: o cliente exibe o que recebeu, sem
    recortar de novo — duas regras de corte divergiriam no primeiro ajuste.
    """

    page_number: int
    snippet: str
    chunk_index: int
    score: float


class MessageResponse(BaseModel):
    """Uma mensagem do histórico, com as citações presas à resposta que as gerou."""

    id: int
    role: MessageRole
    content: str
    citations: list[CitationResponse]
    truncated: bool
    created_at: datetime
