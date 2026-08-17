"""Logging estruturado em JSON.

`structlog` foi escolhido pelo binding de contexto: `request_id` é amarrado uma
vez, no middleware, e reaparece em todo evento emitido durante a requisição e
durante a task de background que ela agenda. É o que faz uma ingestão inteira
caber num único `grep`, sem repetir o campo em cada chamada.

Proibido em log, sob qualquer nível: chave de API, `DATABASE_URL` e conteúdo
integral de chunk ou de PDF.
"""

from typing import Any

import structlog

REQUEST_ID_KEY = "request_id"
DOCUMENT_ID_KEY = "document_id"


def configure_logging() -> None:
    """Configura o structlog para emitir uma linha JSON por evento.

    Chamado no lifespan da aplicação. É idempotente: reconfigurar apenas
    substitui a cadeia de processadores.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        # DEBUG e não INFO: `embedding.batch` é catalogado como debug em §4.4, e o
        # AC-18 exige encontrar no log um evento por lote de embedding. Com o
        # filtro em INFO os dois requisitos não podem valer ao mesmo tempo.
        wrapper_class=structlog.make_filtering_bound_logger(10),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> Any:
    """Devolve um logger amarrado ao módulo que o pediu."""
    return structlog.get_logger(name)


def bind_request_id(request_id: str) -> None:
    """Amarra o `request_id` ao contexto da task assíncrona corrente."""
    structlog.contextvars.bind_contextvars(**{REQUEST_ID_KEY: request_id})


def bind_document_id(document_id: str) -> None:
    """Amarra o `document_id` ao contexto, para os eventos da ingestão o herdarem.

    Amarrado uma vez no início do pipeline em vez de repetido em cada chamada:
    é o que permite `grep` por documento sem que cada etapa lembre do campo.
    """
    structlog.contextvars.bind_contextvars(**{DOCUMENT_ID_KEY: document_id})


def clear_request_context() -> None:
    """Limpa o contexto amarrado, para que ele não vaze entre requisições."""
    structlog.contextvars.clear_contextvars()
