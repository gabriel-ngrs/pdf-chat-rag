"""Adapter de embeddings: lote, backoff, normalização e sigilo da chave.

Nenhum teste deste arquivo chama a API real — o transporte é sempre um dublê.
A conferência contra a API de verdade vive em `scripts/check_embeddings.py` e o
resultado está registrado em `eval/README.md`.
"""

import logging
import math
import random
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
import structlog
from google.genai import errors, types
from structlog.testing import capture_logs

from app.adapters.gemini import (
    MIN_SECRET_FRAGMENT,
    TASK_TYPE_DOCUMENT,
    TASK_TYPE_QUERY,
    EmbeddingPayloadError,
    EmbeddingProviderError,
    EmbeddingQuotaError,
    GeminiEmbeddingClient,
    MissingApiKeyError,
    backoff_delay,
    l2_normalize,
    sanitize_message,
)
from app.config import Settings

FAKE_KEY = "AIzaSyD-fake-key-para-teste-0123456789"


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


def test_falha_de_rede_e_tratada_como_transitoria() -> None:
    models = FakeModels(failures=[TimeoutError("conexão expirou"), None])
    client = build_client(models)

    assert len(client.embed_documents(["gato"])) == 1
    assert len(models.calls) == 2


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
