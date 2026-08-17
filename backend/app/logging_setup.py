"""Logging estruturado em JSON.

`structlog` foi escolhido pelo binding de contexto: `request_id` é amarrado uma
vez, no middleware, e reaparece em todo evento emitido durante a requisição e
durante a task de background que ela agenda. É o que faz uma ingestão inteira
caber num único `grep`, sem repetir o campo em cada chamada.

Proibido em log, sob qualquer nível: chave de API, `DATABASE_URL` e conteúdo
integral de chunk ou de PDF.
"""

import re
from collections.abc import MutableMapping
from functools import lru_cache
from typing import Any

import structlog

from app.config import get_settings

REQUEST_ID_KEY = "request_id"
DOCUMENT_ID_KEY = "document_id"

REDACTED = "[REDACTED]"

# Abaixo disto um "fragmento" deixa de ser identificável e vira ruído: 8
# caracteres da chave já bastam para reconhecê-la, 3 não.
MIN_SECRET_FRAGMENT = 8

# O provedor às vezes ecoa a URL da requisição, que leva a chave em `?key=`.
_KEY_QUERY_PATTERN = re.compile(r"(?i)((?:api[_-]?)?key=)[^&\s\"']+")


@lru_cache(maxsize=4)
def _fragments(secret: str) -> frozenset[str]:
    """Todos os pedaços de `MIN_SECRET_FRAGMENT` caracteres do segredo."""
    return frozenset(
        secret[start : start + MIN_SECRET_FRAGMENT]
        for start in range(len(secret) - MIN_SECRET_FRAGMENT + 1)
    )


def _carries_fragment(text: str, secret: str) -> bool:
    """Diz, em tempo linear, se vale a pena pagar a redação completa.

    A redação exaustiva é quadrática no tamanho do segredo; como ela roda em
    todo evento de log, o caminho comum precisa ser barato.
    """
    known = _fragments(secret)
    return any(
        text[start : start + MIN_SECRET_FRAGMENT] in known
        for start in range(len(text) - MIN_SECRET_FRAGMENT + 1)
    )


def redact_secrets(text: str, secret: str) -> str:
    """Remove do texto o segredo e qualquer fragmento reconhecível dele.

    Fragmento, e não apenas o segredo inteiro, porque uma URL ecoada pode
    trazer a chave truncada — meia chave em log já é vazamento.

    A redação de `key=` na query string roda **sempre**, inclusive quando o
    segredo configurado é desconhecido: ela não depende de saber qual é a
    chave, e uma URL ecoada pelo provedor é o vetor de vazamento mais comum.
    Condicioná-la ao segredo conhecido já produziu um falso verde aqui.
    """
    cleaned = _KEY_QUERY_PATTERN.sub(rf"\1{REDACTED}", text)
    if len(secret) < MIN_SECRET_FRAGMENT or not _carries_fragment(cleaned, secret):
        return cleaned
    for length in range(len(secret), MIN_SECRET_FRAGMENT - 1, -1):
        for start in range(len(secret) - length + 1):
            cleaned = cleaned.replace(secret[start : start + length], REDACTED)
    return cleaned


def redact_processor(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Apaga a chave de API de qualquer campo do evento, inclusive do traceback.

    Roda **depois** de `format_exc_info`, quando o traceback já é string: é
    exatamente ali que um segredo vaza sem ninguém ver, porque a mensagem crua
    da exceção entra no log sem passar por nenhum tratamento do domínio.

    A redação vive aqui, e não só no adapter, de propósito. No adapter ela
    dependeria de a exceção ser de um tipo previsto — e uma que não fosse (uma
    `httpx.ReadTimeout`, por exemplo, que não é `TimeoutError` nem `OSError`)
    chegaria ao catch-all do pipeline com a chave dentro. Redigir na borda de
    renderização cobre a classe inteira do problema, e não os casos lembrados.
    """
    secret = get_settings().gemini_api_key
    return {
        key: redact_secrets(value, secret) if isinstance(value, str) else value
        for key, value in event_dict.items()
    }


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
            # Depois do format_exc_info e antes do renderer: é a última posição
            # em que o traceback ainda é inspecionável como string.
            redact_processor,
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
