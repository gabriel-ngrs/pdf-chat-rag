"""Adapter do Gemini: embeddings e chat.

Da metade de embeddings: lote, backoff, normalização e sigilo da chave. Da
metade de chat: a tradução do orçamento de raciocínio para o que o SDK aceita,
o descarte de pedaço sem texto, o retry na abertura do stream e o prazo do
turno.

Nenhum teste deste arquivo chama a API real — o transporte é sempre um dublê.
A conferência contra a API de verdade vive em `scripts/check_embeddings.py` e o
resultado está registrado em `eval/README.md`.
"""

import asyncio
import logging
import math
import random
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
import structlog
from google.genai import errors, types
from structlog.testing import capture_logs

from app.adapters.gemini import (
    CHAT_MAX_OUTPUT_TOKENS,
    CHAT_TEMPERATURE,
    CONDENSATION_MAX_OUTPUT_TOKENS,
    TASK_TYPE_DOCUMENT,
    TASK_TYPE_QUERY,
    ChatProviderError,
    ChatQuotaError,
    EmbeddingPayloadError,
    EmbeddingProviderError,
    EmbeddingQuotaError,
    GeminiChatClient,
    GeminiEmbeddingClient,
    MissingApiKeyError,
    backoff_delay,
    l2_normalize,
    sanitize_message,
)
from app.config import Settings
from app.logging_setup import MIN_SECRET_FRAGMENT

FAKE_KEY = "AIzaSyD-fake-key-para-teste-0123456789"

# Teto de segurança dos testes que exercitam prazo: bem acima do prazo que o
# cliente deveria aplicar, e bem abaixo da paciência de quem roda a suíte.
GUARDA_SEGUNDOS = 5.0

# Prazo curto usado para provocar o estouro — folgado de propósito.
#
# Com 0,05 s o teste ficava intermitente, e o motivo não era corrida na
# asserção: numa máquina carregada o orçamento acabava **antes da primeira
# leitura**, o `wait_for` cancelava sem nunca iniciar o corpo do gerador, e um
# gerador que não começou não tem `finally` para rodar — `closed` ficava falso
# por comportamento correto. Medido: 17 falhas em 30 com a CPU ocupada e 0 em 40
# ociosa; com 0,5 s, 0 em 25 sob a mesma carga. Meio segundo é o que separa
# "o provedor emudeceu" de "a máquina engasgou".
PRAZO_CURTO_SEGUNDOS = 0.5


class FakeModels:
    """Transporte falso: registra cada chamada e devolve vetores previsíveis.

    `failures` é consumida uma entrada por chamada; `None` significa sucesso.
    """

    def __init__(
        self,
        failures: list[Exception | None] | None = None,
        vectors_per_call: int | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._failures = list(failures or [])
        self._vectors_per_call = vectors_per_call

    def embed_content(
        self, *, model: str, contents: Any, config: types.EmbedContentConfig
    ) -> types.EmbedContentResponse:
        texts = list(contents)
        self.calls.append({"model": model, "texts": texts, "config": config})
        if self._failures:
            failure = self._failures.pop(0)
            if failure is not None:
                raise failure
        total = self._vectors_per_call if self._vectors_per_call is not None else len(texts)
        return types.EmbedContentResponse(
            embeddings=[
                types.ContentEmbedding(values=[float(index + 1), 2.0, 3.0])
                for index in range(total)
            ]
        )


class FakeClient:
    """Cliente do SDK reduzido ao atributo que o adapter alcança."""

    def __init__(self, models: FakeModels) -> None:
        self.models = models


def build_settings(batch_size: int = 16, api_key: str = FAKE_KEY) -> Settings:
    return Settings(
        _env_file=None,
        gemini_api_key=api_key,
        embedding_batch_size=batch_size,
        embedding_dim=768,
    )


def build_client(
    models: FakeModels,
    *,
    batch_size: int = 16,
    api_key: str = FAKE_KEY,
    max_attempts: int = 5,
    sleeps: list[float] | None = None,
) -> GeminiEmbeddingClient:
    return GeminiEmbeddingClient(
        build_settings(batch_size=batch_size, api_key=api_key),
        client=FakeClient(models),
        sleep=(sleeps.append if sleeps is not None else lambda _seconds: None),
        max_attempts=max_attempts,
        rng=random.Random(7),
    )


@contextmanager
def captured_logs() -> Iterator[list[dict[str, Any]]]:
    """Captura os eventos do structlog, inclusive os de nível debug.

    A configuração é forçada aqui porque `configure_logging()` filtra em info; sem
    isto, `embedding.batch` seria descartado antes de chegar ao capturador.
    """
    previous = structlog.get_config()
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        cache_logger_on_first_use=False,
    )
    try:
        with capture_logs() as entries:
            yield entries
    finally:
        structlog.configure(**previous)


def quota_error() -> errors.ClientError:
    return errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})


def payload_error() -> errors.ClientError:
    return errors.ClientError(400, {"error": {"message": "invalid", "status": "INVALID_ARGUMENT"}})


# --- AC-8: um lote por requisição -------------------------------------------------


@pytest.mark.parametrize(
    ("total", "batch_size", "expected_calls"),
    [(10, 4, 3), (16, 16, 1), (17, 16, 2), (1, 16, 1), (48, 16, 3)],
)
def test_faz_ceil_de_n_sobre_b_requisicoes(
    total: int, batch_size: int, expected_calls: int
) -> None:
    models = FakeModels()
    client = build_client(models, batch_size=batch_size)

    vectors = client.embed_documents([f"chunk {index}" for index in range(total)])

    assert len(models.calls) == expected_calls == math.ceil(total / batch_size)
    assert len(vectors) == total
    assert sum(len(call["texts"]) for call in models.calls) == total


def test_lista_vazia_nao_chama_o_provedor() -> None:
    models = FakeModels()

    assert build_client(models).embed_documents([]) == []
    assert models.calls == []


# --- AC-9: backoff no transitório, falha imediata no permanente -------------------


def test_429_na_primeira_chamada_aciona_backoff_e_conclui() -> None:
    models = FakeModels(failures=[quota_error(), None])
    sleeps: list[float] = []
    client = build_client(models, sleeps=sleeps)

    with captured_logs() as entries:
        vectors = client.embed_documents(["gato"])

    assert len(vectors) == 1
    assert len(models.calls) == 2
    assert len(sleeps) == 1 and sleeps[0] > 0
    retries = [entry for entry in entries if entry["event"] == "embedding.retry"]
    assert [entry["attempt"] for entry in retries] == [1]
    assert retries[0]["log_level"] == "warning"
    assert retries[0]["reason"]


def test_400_de_payload_nao_repete_e_falha_com_mensagem_propria() -> None:
    models = FakeModels(failures=[payload_error()])
    sleeps: list[float] = []
    client = build_client(models, sleeps=sleeps)

    with pytest.raises(EmbeddingPayloadError) as erro:
        client.embed_documents(["gato"])

    assert len(models.calls) == 1
    assert sleeps == []
    assert str(erro.value) == "O provedor de IA recusou o conteúdo enviado."
    assert erro.value.code == "erro_interno"


def test_429_persistente_esgota_as_tentativas_e_vira_erro_de_quota() -> None:
    models = FakeModels(failures=[quota_error() for _ in range(5)])
    sleeps: list[float] = []
    client = build_client(models, max_attempts=3, sleeps=sleeps)

    with pytest.raises(EmbeddingQuotaError) as erro:
        client.embed_documents(["gato"])

    assert len(models.calls) == 3
    assert len(sleeps) == 2
    assert erro.value.code == "limite_de_uso"
    assert erro.value.status_code == 429


@pytest.mark.parametrize(
    "falha",
    [
        pytest.param(TimeoutError("conexão expirou"), id="TimeoutError da stdlib"),
        pytest.param(OSError("conexão recusada"), id="OSError da stdlib"),
        # As três abaixo são as que o cliente real produz. Nenhuma é subclasse de
        # TimeoutError nem de OSError: com a captura anterior, uma oscilação de
        # rede não era re-tentada nenhuma vez e a exceção escapava crua.
        pytest.param(httpx.ReadTimeout("leitura expirou"), id="httpx.ReadTimeout"),
        pytest.param(httpx.ConnectError("sem rota para o host"), id="httpx.ConnectError"),
        pytest.param(httpx.RemoteProtocolError("conexão cortada"), id="httpx.RemoteProtocolError"),
    ],
)
def test_falha_de_rede_e_tratada_como_transitoria(falha: Exception) -> None:
    """Toda falha de transporte é re-tentada, inclusive a do cliente real.

    O teste antigo usava só `OSError`, que o SDK nunca levanta — era verde sobre
    um caminho que o sistema não percorre.
    """
    models = FakeModels(failures=[falha, None])
    client = build_client(models)

    assert len(client.embed_documents(["gato"])) == 1
    assert len(models.calls) == 2


def test_excecao_do_httpx_nao_escapa_crua_do_adapter() -> None:
    """Esgotadas as tentativas, o erro sobe como domínio — nunca como httpx.

    Escapar cru levaria a exceção ao catch-all do pipeline, que a transformaria
    num `erro_interno` genérico em vez da mensagem específica.
    """
    models = FakeModels(failures=[httpx.ReadTimeout("expirou")] * 3)
    client = build_client(models, max_attempts=3)

    with pytest.raises(EmbeddingProviderError):
        client.embed_documents(["gato"])

    assert len(models.calls) == 3


def test_erro_permanente_de_credencial_nao_repete() -> None:
    models = FakeModels(failures=[errors.ClientError(403, {"error": {"message": "denied"}})])
    sleeps: list[float] = []
    client = build_client(models, sleeps=sleeps)

    with pytest.raises(EmbeddingProviderError):
        client.embed_documents(["gato"])

    assert len(models.calls) == 1
    assert sleeps == []


def test_backoff_cresce_e_respeita_o_teto() -> None:
    rng = random.Random(1)
    delays = [backoff_delay(attempt, rng) for attempt in range(1, 8)]

    assert delays[0] < delays[2] < delays[4]
    assert all(0 < delay <= 8.0 for delay in delays)


# --- AC-10: norma L2 e task_type ---------------------------------------------------


def test_vetores_saem_com_norma_l2_um() -> None:
    models = FakeModels()
    client = build_client(models)

    vectors = client.embed_documents(["gato", "cachorro"])
    query = client.embed_query("gato")

    for vector in [*vectors, query]:
        assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, abs_tol=1e-6)


def test_normalizacao_e_pura_e_preserva_direcao() -> None:
    normalized = l2_normalize([3.0, 4.0])

    assert math.isclose(math.sqrt(sum(v * v for v in normalized)), 1.0, abs_tol=1e-6)
    assert normalized == [0.6, 0.8]


def test_vetor_nulo_nao_passa_como_normalizado() -> None:
    with pytest.raises(EmbeddingProviderError):
        l2_normalize([0.0, 0.0])


def test_task_type_distinto_entre_documento_e_pergunta() -> None:
    models = FakeModels()
    client = build_client(models)

    client.embed_documents(["um chunk"])
    client.embed_query("uma pergunta")

    task_types = [call["config"].task_type for call in models.calls]
    assert task_types == [TASK_TYPE_DOCUMENT, TASK_TYPE_QUERY]
    assert TASK_TYPE_DOCUMENT != TASK_TYPE_QUERY


def test_toda_requisicao_pede_a_dimensao_do_contrato() -> None:
    models = FakeModels()
    client = build_client(models)

    client.embed_documents(["um chunk"])

    assert models.calls[0]["config"].output_dimensionality == 768
    assert models.calls[0]["model"] == "gemini-embedding-001"


def test_embed_query_devolve_um_unico_vetor_normalizado() -> None:
    models = FakeModels()
    client = build_client(models)

    vector = client.embed_query("qual é o prazo?")

    assert len(models.calls) == 1
    assert models.calls[0]["texts"] == ["qual é o prazo?"]
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, abs_tol=1e-6)


def test_resposta_agregada_e_recusada() -> None:
    """Um vetor só para três textos é o modo de falha que corrompe o retrieval."""
    models = FakeModels(vectors_per_call=1)
    client = build_client(models)

    with pytest.raises(EmbeddingProviderError):
        client.embed_documents(["gato", "cachorro", "mecânica quântica"])


# --- AC-13 e AC-19: a chave nunca escapa ------------------------------------------


def test_sanitiza_a_chave_inteira() -> None:
    limpo = sanitize_message(f"falha usando {FAKE_KEY} agora", FAKE_KEY)

    assert limpo == "falha usando [REDACTED] agora"


def test_sanitiza_fragmento_da_chave() -> None:
    fragmento = FAKE_KEY[:12]

    limpo = sanitize_message(f"chave truncada: {fragmento}...", FAKE_KEY)

    assert fragmento not in limpo
    assert "[REDACTED]" in limpo


def test_sanitiza_a_chave_na_query_string_da_url() -> None:
    limpo = sanitize_message(
        "GET https://api.exemplo/v1:embedContent?key=OUTRA-CHAVE-QUALQUER&alt=json",
        FAKE_KEY,
    )

    assert "OUTRA-CHAVE-QUALQUER" not in limpo
    assert "alt=json" in limpo


def test_sanitizacao_nao_mutila_texto_sem_segredo() -> None:
    assert sanitize_message("erro comum sem segredo", "") == "erro comum sem segredo"
    assert sanitize_message("erro comum sem segredo", FAKE_KEY) == "erro comum sem segredo"


def test_chave_nao_aparece_na_excecao_nem_no_log() -> None:
    """Caminho ponta a ponta: o provedor ecoa a chave e nada dela pode sobrar."""
    vazamento = errors.ClientError(
        400,
        {
            "error": {
                "message": (
                    f"API key not valid: {FAKE_KEY} "
                    f"(GET https://api.exemplo/v1:embedContent?key={FAKE_KEY})"
                ),
                "status": "INVALID_ARGUMENT",
            }
        },
    )
    models = FakeModels(failures=[vazamento])
    client = build_client(models)

    with captured_logs() as entries, pytest.raises(EmbeddingPayloadError) as erro:
        client.embed_documents(["gato"])

    assert FAKE_KEY not in str(erro.value)
    assert FAKE_KEY not in repr(erro.value)
    assert erro.value.__cause__ is None and erro.value.__suppress_context__
    assert entries, "o caminho de erro precisa registrar algo para o teste ter valor"
    serializado = repr(entries)
    assert FAKE_KEY not in serializado
    assert FAKE_KEY[:MIN_SECRET_FRAGMENT] not in serializado
    assert any(entry["event"] == "embedding.failed" for entry in entries)


def test_chave_nao_aparece_no_log_de_retry() -> None:
    models = FakeModels(
        failures=[errors.ClientError(429, {"error": {"message": f"quota for {FAKE_KEY}"}}), None]
    )
    client = build_client(models)

    with captured_logs() as entries:
        client.embed_documents(["gato"])

    assert FAKE_KEY not in repr(entries)
    assert FAKE_KEY[:MIN_SECRET_FRAGMENT] not in repr(entries)


def test_chave_ausente_falha_com_erro_de_dominio_em_pt_br() -> None:
    """Sem cliente injetado o adapter precisa da chave — e cobra no uso, não no import."""
    client = GeminiEmbeddingClient(build_settings(api_key=""))

    with pytest.raises(MissingApiKeyError) as erro:
        client.embed_query("qualquer coisa")

    assert str(erro.value) == "A chave da API de IA não está configurada no servidor."


# --- observabilidade do lote -------------------------------------------------------


def test_emite_embedding_batch_por_lote() -> None:
    models = FakeModels()
    client = build_client(models, batch_size=2)

    with captured_logs() as entries:
        client.embed_documents(["a", "b", "c"])

    lotes = [entry for entry in entries if entry["event"] == "embedding.batch"]
    assert [entry["batch_index"] for entry in lotes] == [0, 1]
    assert [entry["batch_size"] for entry in lotes] == [2, 1]
    assert all(entry["duration_ms"] >= 0 for entry in lotes)
    assert all(entry["log_level"] == "debug" for entry in lotes)


# --- Cliente de chat: configuração, streaming, retry e prazo ----------------------
#
# O transporte continua sendo dublê. O que muda em relação aos testes de
# embedding acima é a face do SDK: o cliente de chat fala com `client.aio.models`,
# porque o cancelamento precisa chegar ao provedor quando quem pergunta desiste.


class FakeAsyncModels:
    """`client.aio.models` sem rede: devolve os pedaços que o teste combinar.

    `stream_failures` é consumida uma entrada por tentativa de **abertura** do
    stream; `None` significa sucesso. É assim que o teste exercita o retry sem
    esperar nenhum backoff real.
    """

    def __init__(
        self,
        *,
        pieces: tuple[str | None, ...] = ("olá", " mundo"),
        text: str = "  pergunta reescrita  ",
        stream_failures: list[Exception | None] | None = None,
        stall: bool = False,
    ) -> None:
        self.pieces = pieces
        self.text = text
        self.configs: list[types.GenerateContentConfig] = []
        self.models_pedidos: list[str] = []
        self.closed = False
        self._stream_failures = list(stream_failures or [])
        self._stall = stall

    async def generate_content(
        self, *, model: str, contents: Any, config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        self.models_pedidos.append(model)
        self.configs.append(config)
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=[types.Part(text=self.text)], role="model")
                )
            ]
        )

    async def generate_content_stream(
        self, *, model: str, contents: Any, config: types.GenerateContentConfig
    ) -> AsyncIterator[types.GenerateContentResponse]:
        self.models_pedidos.append(model)
        self.configs.append(config)
        if self._stream_failures:
            falha = self._stream_failures.pop(0)
            if falha is not None:
                raise falha
        return self._emitir()

    async def _emitir(self) -> AsyncIterator[types.GenerateContentResponse]:
        try:
            if self._stall:
                await asyncio.Event().wait()
            for piece in self.pieces:
                partes = [types.Part(text=piece)] if piece is not None else []
                yield types.GenerateContentResponse(
                    candidates=[types.Candidate(content=types.Content(parts=partes, role="model"))]
                )
        finally:
            self.closed = True


class FakeAsyncApi:
    def __init__(self, models: FakeAsyncModels) -> None:
        self.models = models


class FakeAsyncClient:
    """Cliente do SDK reduzido ao único atributo que o cliente de chat alcança."""

    def __init__(self, models: FakeAsyncModels) -> None:
        self.aio = FakeAsyncApi(models)


def build_chat_client(
    models: FakeAsyncModels, *, max_attempts: int = 2, timeout: float = 60.0, thinking: int = 0
) -> GeminiChatClient:
    """Cliente de chat com o transporte falso e sem espera real de backoff."""

    async def sem_espera(_seconds: float) -> None:
        return None

    return GeminiChatClient(
        Settings(
            _env_file=None,
            gemini_api_key=FAKE_KEY,
            gemini_chat_model="modelo-de-teste",
            gemini_thinking_budget=thinking,
            chat_timeout_seconds=timeout,
        ),
        client=FakeAsyncClient(models),
        sleep=sem_espera,
        max_attempts=max_attempts,
        rng=random.Random(7),
    )


async def coletar(client: GeminiChatClient, prompt: str = "prompt") -> list[str]:
    return [piece async for piece in client.stream_answer(prompt)]


async def test_orcamento_zero_chega_ao_provedor_como_nivel_minimo() -> None:
    """A tradução que o desvio da fase A.4 introduziu, contra o que o SDK aceita.

    `thinking_budget=0` é recusado com `400` pela geração 3.x do modelo; o que
    a configuração do projeto pede — "não raciocine" — passou a viajar como
    nível mínimo. A asserção é sobre o que **chegou ao transporte**, que é onde
    a diferença entre as duas formas existe.
    """
    models = FakeAsyncModels()

    await coletar(build_chat_client(models, thinking=0))

    thinking = models.configs[0].thinking_config
    assert thinking is not None
    assert thinking.thinking_level == types.ThinkingLevel.MINIMAL
    assert thinking.thinking_budget is None


async def test_orcamento_positivo_continua_chegando_como_orcamento() -> None:
    """Quem quiser ligar o raciocínio muda a variável de ambiente, não o código."""
    models = FakeAsyncModels()

    await coletar(build_chat_client(models, thinking=128))

    thinking = models.configs[0].thinking_config
    assert thinking is not None
    assert thinking.thinking_budget == 128
    assert thinking.thinking_level is None


async def test_stream_descarta_pedaco_sem_texto_e_preserva_a_ordem() -> None:
    """§4.2: `chunk.text` pode vir `None`, e emitir isso escreveria "null" na tela."""
    models = FakeAsyncModels(pieces=("primeiro ", None, "segundo"))

    assert await coletar(build_chat_client(models)) == ["primeiro ", "segundo"]


async def test_stream_pede_o_modelo_configurado_com_o_teto_de_saida_do_chat() -> None:
    models = FakeAsyncModels()

    await coletar(build_chat_client(models))

    assert models.models_pedidos == ["modelo-de-teste"]
    assert models.configs[0].max_output_tokens == CHAT_MAX_OUTPUT_TOKENS
    assert models.configs[0].temperature == CHAT_TEMPERATURE


async def test_stream_fecha_o_iterador_do_provedor_ao_terminar() -> None:
    """FR-12: a conexão com o provedor não fica aberta depois do último pedaço."""
    models = FakeAsyncModels()

    await coletar(build_chat_client(models))

    assert models.closed is True


async def test_generate_devolve_o_texto_podado_com_o_teto_da_condensacao() -> None:
    models = FakeAsyncModels(text="  Quais serviços a YAITEC oferece?  ")
    client = build_chat_client(models)

    assert await client.generate("prompt", timeout=5) == "Quais serviços a YAITEC oferece?"
    assert models.configs[0].max_output_tokens == CONDENSATION_MAX_OUTPUT_TOKENS


async def test_falha_transitoria_na_abertura_do_stream_e_re_tentada_uma_vez() -> None:
    models = FakeAsyncModels(stream_failures=[httpx.ConnectError("rede caiu"), None])

    assert await coletar(build_chat_client(models)) == ["olá", " mundo"]


async def test_falha_transitoria_persistente_esgota_as_tentativas() -> None:
    models = FakeAsyncModels(stream_failures=[TimeoutError(), TimeoutError()])

    with pytest.raises(ChatProviderError):
        await coletar(build_chat_client(models))


async def test_quota_do_chat_vira_erro_de_quota_e_nao_de_provedor() -> None:
    models = FakeAsyncModels(stream_failures=[quota_error(), quota_error()])

    with pytest.raises(ChatQuotaError):
        await coletar(build_chat_client(models))


async def test_status_nao_retentavel_desiste_na_primeira_tentativa() -> None:
    """O `404` do modelo descontinuado é o caso real: repetir não muda nada."""
    models = FakeAsyncModels(
        stream_failures=[
            errors.ClientError(404, {"error": {"message": "modelo sumiu", "status": "NOT_FOUND"}}),
            None,
        ]
    )

    with pytest.raises(ChatProviderError):
        await coletar(build_chat_client(models))
    # A segunda entrada da lista continua lá: não houve segunda tentativa.
    assert models.models_pedidos == ["modelo-de-teste"]


async def test_provedor_que_emudece_no_meio_do_stream_estoura_o_prazo_do_turno() -> None:
    """`CHAT_TIMEOUT_SECONDS` é prazo de verdade, não configuração decorativa.

    Sem ele, um provedor que **abre** o stream e para de emitir prenderia o
    turno até o `proxy_read_timeout` do nginx derrubar a conexão, quatro
    minutos depois — e só então a resposta parcial seria gravada.

    O prazo é curto e o stream **precisa ter sido aberto**: é essa asserção que
    faz o teste morder o laço de leitura. Com um prazo que estoura antes da
    abertura, o `stall` ficaria inerte e apagar o prazo de dentro do laço
    deixaria a suíte verde — o defeito voltaria sem sinal nenhum.
    """
    models = FakeAsyncModels(stall=True)

    with pytest.raises(ChatProviderError):
        # A rede de segurança de fora existe para o modo de falha: sem o prazo
        # dentro do laço, este teste **travaria para sempre** em vez de falhar,
        # e uma suíte pendurada é pior que uma suíte vermelha.
        await asyncio.wait_for(
            coletar(build_chat_client(models, timeout=PRAZO_CURTO_SEGUNDOS)), GUARDA_SEGUNDOS
        )

    assert models.models_pedidos == ["modelo-de-teste"], "o stream nem chegou a ser aberto"
    assert models.closed is True, "o iterador do provedor ficou aberto após o estouro"


async def test_prazo_ja_estourado_falha_antes_mesmo_de_abrir_o_stream() -> None:
    """O prazo vale do início do turno, e não a partir do primeiro pedaço.

    É a outra metade do mesmo contrato: quem chega sem tempo nenhum não gasta
    uma chamada ao provedor para descobrir isso.
    """
    models = FakeAsyncModels(stall=True)

    with pytest.raises(ChatProviderError):
        await coletar(build_chat_client(models, timeout=0))

    assert models.models_pedidos == []


async def test_chave_ausente_falha_antes_de_qualquer_chamada_de_chat() -> None:
    client = GeminiChatClient(Settings(_env_file=None, gemini_api_key=""))

    with pytest.raises(MissingApiKeyError):
        await client.generate("prompt", timeout=5)
