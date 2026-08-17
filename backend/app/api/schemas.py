"""Schemas de resposta da API.

São a fonte que o frontend espelha em `types.ts`. Mudar um campo aqui é mudança
quebradora de contrato entre os dois tracks.
"""

from pydantic import BaseModel


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
