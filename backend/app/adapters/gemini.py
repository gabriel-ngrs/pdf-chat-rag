"""Adapter de embeddings do Gemini.

É o único ponto do sistema que fala com a rede, e o único onde um erro silencioso
corrompe tudo a jusante sem quebrar teste nenhum. Daí as três garantias que este
módulo carrega: um vetor por texto (checado em runtime, não só no script de
verificação), norma L2 igual a 1 e nenhum fragmento da chave em log ou exceção.

O contrato de embedding — modelo, dimensão 768, `task_type` e lote — é decisão
fechada da spec e foi verificado contra a API real por `scripts/check_embeddings.py`;
o registro está em `eval/README.md`.

As exceções específicas do provedor nascem aqui, e não em `app.errors`, porque
são detalhe deste adapter; herdam de `AppError` para continuarem saindo no
envelope único `{code, message}`.
"""

import math
import random
import re
import time
from collections.abc import Callable, Iterator, Sequence
from typing import NoReturn, Protocol

from google.genai import Client, errors, types

from app.config import Settings, get_settings
from app.errors import AppError, InternalError, RateLimitError
from app.logging_setup import get_logger

logger = get_logger(__name__)

TASK_TYPE_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_TYPE_QUERY = "RETRIEVAL_QUERY"

REDACTED = "[REDACTED]"

# Abaixo disto um "fragmento" deixa de ser identificável e vira ruído: trechos de
# 8 caracteres da chave já bastam para reconhecê-la, trechos de 3 não.
MIN_SECRET_FRAGMENT = 8

DEFAULT_MAX_ATTEMPTS = 5
INITIAL_BACKOFF_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 8.0
PAYLOAD_STATUS = 400
QUOTA_STATUS = 429
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

MISSING_KEY_MESSAGE = "A chave da API de IA não está configurada no servidor."
QUOTA_MESSAGE = "O limite de uso da IA foi atingido. Tente de novo em alguns minutos."
PAYLOAD_MESSAGE = "O provedor de IA recusou o conteúdo enviado."
PROVIDER_MESSAGE = "Não foi possível gerar os embeddings do documento. Tente de novo."

# O provedor às vezes ecoa a URL da requisição, que leva a chave em `?key=`.
_KEY_QUERY_PATTERN = re.compile(r"(?i)((?:api[_-]?)?key=)[^&\s\"']+")


class MissingApiKeyError(InternalError):
    """`GEMINI_API_KEY` não está definida no ambiente do servidor."""


class EmbeddingQuotaError(RateLimitError):
    """A quota do provedor foi atingida e o backoff não foi suficiente."""


class EmbeddingPayloadError(InternalError):
    """O provedor recusou o payload (`400`); repetir não muda o resultado."""


class EmbeddingProviderError(InternalError):
    """O provedor falhou de um jeito que o adapter não sabe contornar."""


class EmbeddingClient(Protocol):
    """O que o pipeline de ingestão e o retrieval consomem.

    Protocolo e não classe base: é o que permite o dublê dos testes existir sem
    herança e sem importar o SDK do provedor.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class EmbedContentApi(Protocol):
    """A fatia do SDK que este adapter usa (`client.models`)."""

    def embed_content(
        self,
        *,
        model: str,
        contents: types.ContentListUnion,
        config: types.EmbedContentConfig,
    ) -> types.EmbedContentResponse: ...


class GenaiClient(Protocol):
    """Cliente do SDK, reduzido ao que o adapter alcança."""

    @property
    def models(self) -> EmbedContentApi: ...


def sanitize_message(message: str, secret: str) -> str:
    """Remove da mensagem a chave de API e qualquer fragmento reconhecível dela.

    Fragmento, e não apenas a chave inteira, porque o provedor pode ecoar a URL
    com a chave truncada — meia chave em log já é vazamento.
    """
    cleaned = _KEY_QUERY_PATTERN.sub(rf"\1{REDACTED}", message)
    if len(secret) < MIN_SECRET_FRAGMENT:
        return cleaned
    for length in range(len(secret), MIN_SECRET_FRAGMENT - 1, -1):
        for start in range(len(secret) - length + 1):
            cleaned = cleaned.replace(secret[start : start + length], REDACTED)
    return cleaned


def l2_normalize(vector: Sequence[float]) -> list[float]:
    """Devolve o vetor com norma L2 igual a 1.

    Obrigatório: o modelo só entrega vetor normalizado quando a dimensão é 3072,
    e pedimos 768. Sem isto a distância de cosseno da busca mente.
    """
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        raise EmbeddingProviderError(PROVIDER_MESSAGE)
    return [value / norm for value in vector]


def backoff_delay(attempt: int, rng: random.Random) -> float:
    """Espera exponencial com jitter para a tentativa dada (1 é a primeira).

    Metade fixa e metade sorteada: a parte fixa garante que a espera cresce, a
    sorteada evita que lotes concorrentes voltem todos no mesmo instante.
    """
    capped = min(INITIAL_BACKOFF_SECONDS * 2.0 ** (attempt - 1), MAX_BACKOFF_SECONDS)
    return capped / 2 + rng.uniform(0.0, capped / 2)


def _batches(texts: Sequence[str], size: int) -> Iterator[list[str]]:
    """Fatia os textos em lotes de no máximo `size` itens."""
    step = max(1, size)
    for start in range(0, len(texts), step):
        yield list(texts[start : start + step])


class GeminiEmbeddingClient:
    """Implementação de `EmbeddingClient` sobre o SDK `google-genai`.

    O cliente do SDK, o `sleep` e o gerador de aleatoriedade entram pelo
    construtor para que os testes exercitem o backoff sem rede e sem espera real.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: GenaiClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        rng: random.Random | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_settings()
        self._client = client
        self._sleep = sleep
        self._max_attempts = max(1, max_attempts)
        # O sorteio só espalha o jitter do backoff — não gera segredo nem token,
        # então um gerador criptográfico aqui seria custo sem ganho (daí o nosec).
        self._rng = rng if rng is not None else random.Random()  # nosec B311

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embeda os chunks de um documento, em lotes de `EMBEDDING_BATCH_SIZE`."""
        vectors: list[list[float]] = []
        batch_size = self._settings.embedding_batch_size
        for batch_index, batch in enumerate(_batches(texts, batch_size)):
            vectors.extend(self._embed_batch(batch, TASK_TYPE_DOCUMENT, batch_index))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Embeda a pergunta do usuário, com o `task_type` de consulta."""
        return self._embed_batch([text], TASK_TYPE_QUERY, 0)[0]

    def _embed_batch(self, texts: list[str], task_type: str, batch_index: int) -> list[list[float]]:
        started = time.perf_counter()
        response = self._request(texts, task_type, batch_index)
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.debug(
            "embedding.batch",
            batch_index=batch_index,
            batch_size=len(texts),
            duration_ms=duration_ms,
        )
        return [l2_normalize(values) for values in self._read_vectors(response, len(texts))]

    def _request(
        self, texts: list[str], task_type: str, batch_index: int
    ) -> types.EmbedContentResponse:
        contents: list[str | types.File | types.Part] = list(texts)
        config = types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self._settings.embedding_dim,
        )
        attempt = 1
        while True:
            try:
                return self._models().embed_content(
                    model=self._settings.gemini_embedding_model,
                    contents=contents,
                    config=config,
                )
            except errors.APIError as exc:
                status = exc.code
                reason = self._sanitize(str(exc))
                if status == PAYLOAD_STATUS:
                    self._fail(reason, status, EmbeddingPayloadError(PAYLOAD_MESSAGE))
                if status not in RETRYABLE_STATUS:
                    self._fail(reason, status, EmbeddingProviderError(PROVIDER_MESSAGE))
            except (TimeoutError, OSError) as exc:
                # Falha de transporte não diz nada sobre o pedido: é transitória.
                status = None
                reason = self._sanitize(f"{type(exc).__name__}: {exc}")

            if attempt >= self._max_attempts:
                exhausted: AppError = (
                    EmbeddingQuotaError(QUOTA_MESSAGE)
                    if status == QUOTA_STATUS
                    else EmbeddingProviderError(PROVIDER_MESSAGE)
                )
                self._fail(reason, status, exhausted)

            logger.warning(
                "embedding.retry",
                attempt=attempt,
                reason=reason,
                batch_index=batch_index,
            )
            self._sleep(backoff_delay(attempt, self._rng))
            attempt += 1

    def _read_vectors(
        self, response: types.EmbedContentResponse, expected: int
    ) -> list[list[float]]:
        """Extrai um vetor por texto, recusando resposta agregada ou vazia.

        A contagem é conferida em runtime mesmo já tendo sido verificada contra a
        API real: se o provedor mudar o comportamento de lote, o sistema precisa
        parar em vez de gravar vetores desalinhados dos chunks.
        """
        embeddings = response.embeddings or []
        if len(embeddings) != expected:
            self._fail(
                f"o provedor devolveu {len(embeddings)} vetores para {expected} textos",
                None,
                EmbeddingProviderError(PROVIDER_MESSAGE),
            )
        vectors: list[list[float]] = []
        for embedding in embeddings:
            if not embedding.values:
                self._fail(
                    "o provedor devolveu um vetor vazio",
                    None,
                    EmbeddingProviderError(PROVIDER_MESSAGE),
                )
            vectors.append(list(embedding.values))
        return vectors

    def _models(self) -> EmbedContentApi:
        """Devolve a API de embedding, criando o cliente real na primeira chamada.

        A chave é exigida aqui, no momento do uso, e não no import: exigi-la no
        import derrubaria a suíte inteira de quem clona o projeto sem `.env`.
        """
        if self._client is None:
            api_key = self._settings.gemini_api_key
            if not api_key:
                raise MissingApiKeyError(MISSING_KEY_MESSAGE)
            self._client = Client(api_key=api_key)
        return self._client.models

    def _sanitize(self, message: str) -> str:
        return sanitize_message(message, self._settings.gemini_api_key)

    def _fail(self, reason: str, status: int | None, error: AppError) -> NoReturn:
        """Registra o motivo já sanitizado e levanta o erro de domínio.

        `from None` é deliberado: encadear a exceção do provedor faria o traceback
        — impresso por qualquer `logger.exception` acima — carregar a mensagem
        crua, que pode conter a chave.
        """
        logger.warning("embedding.failed", reason=reason, status=status, code=error.code)
        raise error from None
