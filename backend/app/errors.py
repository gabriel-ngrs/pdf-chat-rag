"""Envelope de erro único da API e os handlers que o aplicam.

Toda resposta de erro sai como `{"code": ..., "message": ...}`, inclusive as de
validação do framework. O frontend mapeia por `code`, nunca por status: é o que
permite reusar as mesmas mensagens no streaming, onde não há status HTTP.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_setup import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Erro de domínio que sabe como se apresentar ao usuário final.

    Carrega o `code` do envelope, a `message` em pt-BR e o status HTTP
    correspondente, para que o handler não precise traduzir exceção em resposta
    caso a caso.
    """

    code = "erro_interno"
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class FileTooLargeError(AppError):
    """O arquivo enviado excede `MAX_UPLOAD_MB`."""

    code = "arquivo_grande"
    status_code = 413


class InvalidFileError(AppError):
    """O arquivo não é um PDF, ou o payload da requisição é inválido."""

    code = "arquivo_invalido"
    status_code = 422


class NotFoundError(AppError):
    """O recurso pedido não existe."""

    code = "nao_encontrado"
    status_code = 404


class RateLimitError(AppError):
    """A quota do provedor de IA foi atingida."""

    code = "limite_de_uso"
    status_code = 429


class InternalError(AppError):
    """Falha inesperada, apresentada sem detalhe técnico ao usuário."""

    code = "erro_interno"
    status_code = 500


class PdfPageLimitError(AppError):
    """O PDF tem mais páginas do que `MAX_PDF_PAGES` permite.

    É distinta de `FileTooLargeError` porque o arquivo pode caber no limite de
    bytes e ainda assim estourar a quota de embeddings — o usuário precisa
    saber qual dos dois limites ele bateu para conseguir corrigir o envio.
    """

    code = "pdf_muitas_paginas"
    status_code = 422


class PdfTextLimitError(AppError):
    """O texto extraído do PDF passa de `MAX_EXTRACTED_CHARS`."""

    code = "pdf_texto_longo"
    status_code = 422


class PdfWithoutTextError(AppError):
    """O PDF não tem camada de texto — tipicamente é um documento escaneado.

    Tem código próprio porque a ação do usuário é diferente das outras falhas:
    não adianta reenviar o mesmo arquivo, já que OCR está fora do escopo.
    """

    code = "pdf_sem_texto"
    status_code = 422


def error_body(code: str, message: str) -> dict[str, str]:
    """Monta o corpo do envelope de erro."""
    return {"code": code, "message": message}


# Traduz os erros HTTP que o próprio framework levanta (404 de rota inexistente,
# 405 de método errado) para os códigos de §4.3. Status sem código próprio caem
# em `erro_interno`: a tabela de códigos é contrato consumido pelos dois tracks,
# e inventar um código aqui quebraria o mapa do frontend em vez de completá-lo.
_HTTP_ERROR_CODES = {
    404: NotFoundError.code,
    413: FileTooLargeError.code,
    422: InvalidFileError.code,
    429: RateLimitError.code,
}

_HTTP_ERROR_MESSAGES = {
    404: "O endereço pedido não existe.",
    405: "Este endereço não aceita esse método.",
    413: "O arquivo excede o limite de upload.",
    422: "Os dados enviados são inválidos.",
    429: "O limite de uso foi atingido. Tente de novo em alguns minutos.",
}

DEFAULT_HTTP_MESSAGE = "Não foi possível completar a requisição."


def register_error_handlers(app: FastAPI) -> None:
    """Registra os handlers que garantem o envelope único em toda saída de erro.

    O handler genérico existe porque uma exceção não prevista responderia HTML
    de stack trace por default — vazando implementação e quebrando o contrato
    que o frontend consome.
    """

    async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
        error = exc if isinstance(exc, AppError) else InternalError("Erro interno no servidor.")
        logger.warning("request.failed", code=error.code, path=request.url.path)
        return JSONResponse(
            status_code=error.status_code,
            content=error_body(error.code, error.message),
        )

    async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
        logger.warning("request.invalid", path=request.url.path)
        return JSONResponse(
            status_code=422,
            content=error_body(
                InvalidFileError.code,
                "Os dados enviados são inválidos. Confira o formulário e tente de novo.",
            ),
        )

    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("request.unhandled", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_body(
                InternalError.code,
                "Erro interno no servidor. Tente de novo em alguns instantes.",
            ),
        )

    async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
        """Envelopa os erros que o framework levanta por conta própria.

        Sem este handler, `404` de rota inexistente e `405` de método errado
        saem como `{"detail": ...}` — formato que o frontend não mapeia, porque
        ele lê `code` e nunca status. O AC-17 fala de **qualquer** erro 4xx/5xx.
        """
        status_code = getattr(exc, "status_code", 500)
        logger.warning("request.http_error", status=status_code, path=request.url.path)
        return JSONResponse(
            status_code=status_code,
            content=error_body(
                _HTTP_ERROR_CODES.get(status_code, InternalError.code),
                _HTTP_ERROR_MESSAGES.get(status_code, DEFAULT_HTTP_MESSAGE),
            ),
        )

    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
