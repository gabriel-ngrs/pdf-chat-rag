"""Adapter do Gemini: embeddings e geração de chat.

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

import asyncio
import math
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from typing import NoReturn, Protocol

import httpx
from google.genai import Client, errors, types

from app.config import Settings, get_settings
from app.errors import AppError, InternalError, RateLimitError
from app.logging_setup import get_logger, redact_secrets

logger = get_logger(__name__)

TASK_TYPE_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_TYPE_QUERY = "RETRIEVAL_QUERY"

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

# `temperature` baixa porque a tarefa é extrativa: o modelo deve reproduzir o que
# está no contexto, não variar a redação a cada execução.
CHAT_TEMPERATURE = 0.2
CHAT_MAX_OUTPUT_TOKENS = 2048
# A condensação devolve uma única pergunta reescrita. O teto curto é o que impede
# que um modelo em dia inspirado gaste latência escrevendo um parágrafo antes de
# a busca sequer começar.
CONDENSATION_MAX_OUTPUT_TOKENS = 128

# Duas tentativas, e não as cinco do embedding. O `429` do chat é quota por
# minuto: um backoff de segundos não a libera, e a NFR-1 dá cinco segundos até o
# primeiro token — insistir só transformaria um aviso rápido em espera inútil.
CHAT_MAX_ATTEMPTS = 2

CHAT_QUOTA_MESSAGE = "O limite de uso da IA foi atingido. Espere um minuto e pergunte de novo."
CHAT_PROVIDER_MESSAGE = "A IA não conseguiu responder agora. Tente perguntar de novo."

# O nível mínimo de raciocínio que a geração 3.x do modelo oferece. É o que
# substitui `thinking_budget=0`, que ela recusa com `400`.
MINIMUM_THINKING_LEVEL = types.ThinkingLevel.MINIMAL


class MissingApiKeyError(InternalError):
    """`GEMINI_API_KEY` não está definida no ambiente do servidor."""


class EmbeddingQuotaError(RateLimitError):
    """A quota do provedor foi atingida e o backoff não foi suficiente."""


class EmbeddingPayloadError(InternalError):
    """O provedor recusou o payload (`400`); repetir não muda o resultado."""


class EmbeddingProviderError(InternalError):
    """O provedor falhou de um jeito que o adapter não sabe contornar."""


class ChatQuotaError(RateLimitError):
    """A quota do modelo de chat foi atingida.

    Separada de `EmbeddingQuotaError` porque a ação do usuário é outra: aqui
    basta esperar o minuto virar e perguntar de novo, sem reenviar documento.
    """


class ChatProviderError(AppError):
    """O modelo de chat falhou de um jeito que o adapter não sabe contornar.

    Tem `code` próprio (`provedor`, §4.3) em vez de cair em `erro_interno`
    porque a origem da falha é externa: o frontend usa o código para dizer que
    o problema não é a pergunta nem o documento, e oferecer "tentar de novo"
    como ação. O status `502` diz a mesma coisa em HTTP.
    """

    code = "provedor"
    status_code = 502


class EmbeddingClient(Protocol):
    """O que o pipeline de ingestão e o retrieval consomem.

    Protocolo e não classe base: é o que permite o dublê dos testes existir sem
    herança e sem importar o SDK do provedor.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class ChatClient(Protocol):
    """O que um turno de chat consome do provedor de geração.

    Dois métodos porque são duas chamadas de naturezas diferentes: `generate` é
    a chamada única que a condensação faz e cujo resultado só serve se chegar
    dentro do timeout; `stream_answer` é a geração incremental, que precisa
    entregar o primeiro token o quanto antes.

    Protocolo nomeado, e não a classe concreta, porque é ele que dá ao dublê da
    suíte uma interface para implementar — sem isso, testar recusa, timeout de
    condensação e erro mid-stream exigiria rede.
    """

    async def generate(self, prompt: str, *, timeout: float) -> str: ...

    def stream_answer(self, prompt: str) -> AsyncIterator[str]: ...


class GenerateContentApi(Protocol):
    """A fatia assíncrona do SDK que o cliente de chat usa (`client.aio.models`)."""

    async def generate_content(
        self,
        *,
        model: str,
        contents: types.ContentListUnion,
        config: types.GenerateContentConfig,
    ) -> types.GenerateContentResponse: ...

    def generate_content_stream(
        self,
        *,
        model: str,
        contents: types.ContentListUnion,
        config: types.GenerateContentConfig,
    ) -> Awaitable[AsyncIterator[types.GenerateContentResponse]]: ...


class AsyncGenaiApi(Protocol):
    """O `client.aio` do SDK, reduzido ao que o adapter alcança."""

    @property
    def models(self) -> GenerateContentApi: ...


class AsyncGenaiClient(Protocol):
    """Cliente do SDK visto pelo cliente de chat: só a face assíncrona."""

    @property
    def aio(self) -> AsyncGenaiApi: ...


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

    Delega a `logging_setup.redact_secrets`, que é a mesma redação aplicada na
    borda de renderização do log. Uma implementação só: duas divergiriam, e a
    que estivesse errada seria descoberta por um vazamento.

    Aqui a redação continua valendo a pena mesmo com o processador global,
    porque esta mensagem também alimenta o `reason` estruturado — e defesa em
    profundidade num segredo é barata.
    """
    return redact_secrets(message, secret)


def _thinking_config(budget: int) -> types.ThinkingConfig:
    """Traduz o orçamento de raciocínio configurado no que o provedor aceita hoje.

    Zero significa "não raciocine" e é o default do projeto (NFR-1). O modelo
    da geração 3.x não aceita mais essa intenção como orçamento — ela virou o
    nível de raciocínio —, então zero vira o nível mínimo e qualquer valor positivo
    continua sendo orçamento explícito, para quem quiser ligar o raciocínio sem
    trocar de código.
    """
    if budget <= 0:
        return types.ThinkingConfig(thinking_level=MINIMUM_THINKING_LEVEL)
    return types.ThinkingConfig(thinking_budget=budget)


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
            except (TimeoutError, OSError, httpx.TransportError) as exc:
                # Falha de transporte não diz nada sobre o pedido: é transitória.
                #
                # `httpx.TransportError` está aqui porque é a classe que o cliente
                # real produz: o google-genai fala httpx, e ReadTimeout,
                # ConnectError e ConnectTimeout não são subclasse de TimeoutError
                # nem de OSError. Sem ela, uma oscilação de rede de um segundo não
                # era re-tentada nenhuma vez — a exceção escapava crua do adapter
                # e o documento terminava `failed` por um problema transitório.
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


class GeminiChatClient:
    """Implementação de `ChatClient` sobre a face assíncrona do `google-genai`.

    Assíncrono, e não `asyncio.to_thread` como o cliente de embeddings, por um
    motivo de comportamento e não de estilo: quando o usuário fecha a aba, o
    cancelamento precisa chegar ao provedor e parar o consumo de quota (FR-12).
    Uma thread não é cancelável — ela seguiria baixando tokens que ninguém iria
    ler, exatamente o custo que a desconexão deveria evitar.

    O cliente do SDK e o `sleep` entram pelo construtor para que os testes
    exercitem o backoff e os caminhos de erro sem rede e sem espera real.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: AsyncGenaiClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_attempts: int = CHAT_MAX_ATTEMPTS,
        rng: random.Random | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_settings()
        self._client = client
        self._sleep = sleep
        self._max_attempts = max(1, max_attempts)
        # Mesmo caso do cliente de embeddings: o sorteio só espalha o jitter do
        # backoff, não gera segredo nem token (daí o nosec).
        self._rng = rng if rng is not None else random.Random()  # nosec B311

    async def generate(self, prompt: str, *, timeout: float) -> str:
        """Faz a chamada única da condensação e devolve o texto da resposta.

        O `timeout` é do chamador porque quem sabe quanto a espera vale a pena é
        quem tem o fallback na mão: passar do prazo aqui não é erro, é o sinal
        para a condensação desistir e seguir com a query concatenada (FR-4).
        """
        return await asyncio.wait_for(self._generate(prompt), timeout)

    async def stream_answer(self, prompt: str) -> AsyncIterator[str]:
        """Emite os pedaços de texto da resposta à medida que o provedor os produz.

        O `chunk.text` do SDK pode vir `None` — em pedaços que carregam só
        metadado — e emitir isso como token faria a tela mostrar "null" no meio
        da frase. O filtro é aqui, e não no cliente do navegador, porque é aqui
        que a forma do SDK é conhecida.

        Retry acontece só na abertura do stream: uma vez que o primeiro token
        saiu, repetir a chamada duplicaria o texto já exibido na tela.

        `CHAT_TIMEOUT_SECONDS` é o prazo do **turno inteiro**, e não de cada
        pedaço: um provedor que abre o stream e para de emitir prenderia o turno
        até o `proxy_read_timeout` do nginx derrubar a conexão, quatro minutos
        depois, e só então a resposta parcial seria gravada. O prazo é contado
        da abertura, de modo que o tempo gasto para abrir também conta — é o que
        o operador entende ao ler "60 s" no arquivo de configuração.
        """
        deadline = asyncio.get_running_loop().time() + self._settings.chat_timeout_seconds
        stream = await self._with_deadline(self._open_stream(prompt), deadline)
        try:
            while True:
                try:
                    chunk = await self._with_deadline(anext(stream), deadline)
                except StopAsyncIteration:
                    break
                text = chunk.text
                if text:
                    yield text
        except errors.APIError as exc:
            self._fail_chat(self._sanitize(str(exc)), exc.code)
        finally:
            # O iterador do provedor é fechado aqui e não no chamador: quando o
            # cliente desconecta, este `finally` roda pelo `aclose()` do gerador
            # e é o que garante que a conexão com o provedor não fique aberta.
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()

    async def _with_deadline[T](self, awaitable: Awaitable[T], deadline: float) -> T:
        """Espera pelo `awaitable` até o prazo do turno, e desiste com clareza.

        O estouro vira `ChatProviderError` — e não um `TimeoutError` cru —
        porque para quem está do outro lado da tela um provedor que emudece é
        indistinguível de um provedor que falhou, e a ação sugerida é a mesma:
        perguntar de novo. Quem decide se isso vira envelope HTTP ou evento
        `error` é `app.chat`, pelo critério de FR-11.
        """
        remaining = deadline - asyncio.get_running_loop().time()
        try:
            return await asyncio.wait_for(awaitable, max(0.0, remaining))
        except TimeoutError:
            self._fail_chat(
                f"o provedor não respondeu dentro de {self._settings.chat_timeout_seconds}s", None
            )

    async def _generate(self, prompt: str) -> str:
        response = await self._call_with_retry(
            lambda: self._models().generate_content(
                model=self._settings.gemini_chat_model,
                contents=prompt,
                config=self._config(CONDENSATION_MAX_OUTPUT_TOKENS),
            )
        )
        return (response.text or "").strip()

    async def _open_stream(self, prompt: str) -> AsyncIterator[types.GenerateContentResponse]:
        return await self._call_with_retry(
            lambda: self._models().generate_content_stream(
                model=self._settings.gemini_chat_model,
                contents=prompt,
                config=self._config(CHAT_MAX_OUTPUT_TOKENS),
            )
        )

    async def _call_with_retry[T](self, call: Callable[[], Awaitable[T]]) -> T:
        """Executa a chamada, re-tentando o que é transitório e nada além disso.

        A classificação é a mesma do cliente de embeddings (`RETRYABLE_STATUS`),
        e por isso mora nas mesmas constantes: dois mapas de status divergentes
        seriam duas verdades sobre o mesmo provedor.
        """
        attempt = 1
        while True:
            try:
                return await call()
            except errors.APIError as exc:
                status: int | None = exc.code
                reason = self._sanitize(str(exc))
                if status not in RETRYABLE_STATUS:
                    self._fail_chat(reason, status)
            except (TimeoutError, OSError, httpx.TransportError) as exc:
                status = None
                reason = self._sanitize(f"{type(exc).__name__}: {exc}")

            if attempt >= self._max_attempts:
                self._fail_chat(reason, status)

            logger.warning("chat.retry", attempt=attempt, reason=reason)
            await self._sleep(backoff_delay(attempt, self._rng))
            attempt += 1

    def _config(self, max_output_tokens: int) -> types.GenerateContentConfig:
        """Monta a configuração comum às duas chamadas.

        O objetivo é o da NFR-1: **o mínimo de raciocínio possível**, porque RAG
        extrativo não se beneficia dele e ele só adia o primeiro token — a
        métrica que a spec limita a cinco segundos.

        Como pedir esse mínimo mudou de forma entre gerações do modelo, e a
        forma antiga virou erro em vez de ser ignorada: `gemini-3.x` responde
        `400 INVALID_ARGUMENT` a `thinking_budget=0` (medido contra a API real
        no gate da fase A.4) e expõe o mesmo controle como `thinking_level`.
        `GEMINI_THINKING_BUDGET=0` continua sendo a forma de pedir "sem
        raciocínio" no ambiente — o que muda é só como isso chega ao provedor.
        """
        return types.GenerateContentConfig(
            temperature=CHAT_TEMPERATURE,
            max_output_tokens=max_output_tokens,
            thinking_config=_thinking_config(self._settings.gemini_thinking_budget),
        )

    def _models(self) -> GenerateContentApi:
        """Devolve a API assíncrona de geração, criando o cliente na primeira chamada."""
        if self._client is None:
            api_key = self._settings.gemini_api_key
            if not api_key:
                raise MissingApiKeyError(MISSING_KEY_MESSAGE)
            self._client = Client(api_key=api_key)
        return self._client.aio.models

    def _sanitize(self, message: str) -> str:
        return sanitize_message(message, self._settings.gemini_api_key)

    def _fail_chat(self, reason: str, status: int | None) -> NoReturn:
        """Registra o motivo já sanitizado e levanta o erro de domínio do chat.

        `from None` pelo mesmo motivo do cliente de embeddings: encadear a
        exceção do provedor faria o traceback carregar a mensagem crua, que
        pode conter a chave.
        """
        error: AppError = (
            ChatQuotaError(CHAT_QUOTA_MESSAGE)
            if status == QUOTA_STATUS
            else ChatProviderError(CHAT_PROVIDER_MESSAGE)
        )
        logger.warning("chat.provider_failed", reason=reason, status=status, code=error.code)
        raise error from None
