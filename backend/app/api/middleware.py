"""Middleware que dá identidade a cada requisição.

Um `request_id` por requisição, amarrado ao contexto do structlog e devolvido no
header `X-Request-Id`. O header não é enfeite: é o que permite correlacionar o
que apareceu na tela com a linha exata do log.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logging_setup import bind_request_id, clear_request_context

REQUEST_ID_HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Gera (ou aceita) o `request_id` e o propaga para log e resposta.

    Um id vindo do cliente é reaproveitado para não quebrar rastreamento
    externo; na ausência dele, um UUID4 é gerado.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        bind_request_id(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            clear_request_context()
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
