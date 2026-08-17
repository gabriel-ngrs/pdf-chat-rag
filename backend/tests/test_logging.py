"""O contrato de logging de §4.4 e o sigilo da chave de API.

Os testes de rastreabilidade rodam sobre o adapter **real** de embeddings, com o
SDK do provedor substituído por um dublê. É deliberado: `embedding.batch` nasce
dentro do adapter, então trocar o adapter inteiro por um `FakeEmbeddingClient`
apagaria justamente o evento que o AC-18 exige encontrar. Rede continua fora do
teste — o que é falso é o transporte, não a camada sob verificação.
"""

import io
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from google.genai import errors

from app.adapters.gemini import MISSING_KEY_MESSAGE, GeminiEmbeddingClient
from app.api.middleware import REQUEST_ID_HEADER
from app.config import Settings
from app.core.models import DocumentStatus
from app.ingestion import run_ingestion
from tests.factories import build_text_pdf
from tests.fakes import FakeRepository, StubGenaiClient, StubGenaiModels

FAKE_KEY = "AIzaSyD-chave-falsa-para-teste-0123456789"
REQUEST_ID = "req-de-teste-0001"

EVENTOS_DA_INGESTAO = (
    "document.received",
    "document.extracted",
    "document.chunked",
    "embedding.batch",
    "document.ready",
)

PAGINA = (
    "O contrato de logging exige que a ingestao inteira apareca num unico grep "
    "por request_id, do recebimento ate a conclusao do documento. "
)


def documento() -> bytes:
    return build_text_pdf([f"Pagina {numero}. {PAGINA * 3}" for numero in (1, 2)])


def build_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "gemini_api_key": FAKE_KEY,
        "chunk_size": 200,
        "chunk_overlap": 40,
        "embedding_batch_size": 2,
        "embedding_dim": 8,
    }
    return Settings(_env_file=None, **{**base, **overrides})


def build_embedder(
    settings: Settings, *, failures: list[Exception | None] | None = None
) -> GeminiEmbeddingClient:
    """Adapter real com transporte falso, sem espera de backoff e sem rede."""
    return GeminiEmbeddingClient(
        settings,
        client=StubGenaiClient(StubGenaiModels(failures=failures)),
        sleep=lambda _seconds: None,
        max_attempts=2,
    )


def eventos(capturados: list[dict[str, Any]], nome: str) -> list[dict[str, Any]]:
    return [entrada for entrada in capturados if entrada.get("event") == nome]


def texto_de(capturados: list[dict[str, Any]]) -> str:
    """Achata tudo que foi capturado numa string única, que é o alvo do `grep`."""
    return "\n".join(repr(entrada) for entrada in capturados)


# ─── AC-18: rastreabilidade ──────────────────────────────────────────────────


async def test_ingestao_emite_os_eventos_nomeados_de_44(
    build_client: Callable[..., httpx.AsyncClient],
    captured_logs: list[dict[str, Any]],
) -> None:
    """AC-18: recebimento, extração, chunking, cada lote e conclusão aparecem."""
    settings = build_settings()

    async with build_client(embedding_client=build_embedder(settings), config=settings) as client:
        response = await client.post(
            "/api/documents",
            files={"file": ("documento.pdf", documento(), "application/pdf")},
        )

    assert response.status_code == 202
    emitidos = [entrada.get("event") for entrada in captured_logs]
    for esperado in EVENTOS_DA_INGESTAO:
        assert esperado in emitidos


async def test_todos_os_eventos_da_ingestao_carregam_o_mesmo_request_id(
    build_client: Callable[..., httpx.AsyncClient],
    captured_logs: list[dict[str, Any]],
) -> None:
    """AC-18: o id da requisição atravessa a task de background sem se perder.

    É o que permite `docker compose logs backend | grep <request_id>` mostrar a
    ingestão inteira, e não só a linha do POST.
    """
    settings = build_settings()

    async with build_client(embedding_client=build_embedder(settings), config=settings) as client:
        response = await client.post(
            "/api/documents",
            files={"file": ("documento.pdf", documento(), "application/pdf")},
            headers={REQUEST_ID_HEADER: REQUEST_ID},
        )

    assert response.headers[REQUEST_ID_HEADER] == REQUEST_ID
    for nome in EVENTOS_DA_INGESTAO:
        encontrados = eventos(captured_logs, nome)
        assert encontrados, f"o evento {nome} não foi emitido"
        assert all(entrada.get("request_id") == REQUEST_ID for entrada in encontrados)


async def test_os_eventos_de_etapa_reportam_duracao_e_documento(
    build_client: Callable[..., httpx.AsyncClient],
    captured_logs: list[dict[str, Any]],
) -> None:
    """AC-18: cada etapa mede o próprio tempo, como o contrato de §4.4 exige."""
    settings = build_settings()

    async with build_client(embedding_client=build_embedder(settings), config=settings) as client:
        response = await client.post(
            "/api/documents",
            files={"file": ("documento.pdf", documento(), "application/pdf")},
        )

    document_id = response.json()["id"]
    for nome in ("document.extracted", "document.chunked", "embedding.batch"):
        for entrada in eventos(captured_logs, nome):
            assert isinstance(entrada["duration_ms"], int)
    concluido = eventos(captured_logs, "document.ready")
    assert len(concluido) == 1
    assert isinstance(concluido[0]["total_duration_ms"], int)
    assert concluido[0]["chunk_count"] > 0
    assert concluido[0]["document_id"] == document_id


async def test_o_documento_id_acompanha_os_eventos_do_pipeline(
    repository: FakeRepository, captured_logs: list[dict[str, Any]]
) -> None:
    """O `document_id` é amarrado uma vez e herdado, sem repetição em cada chamada."""
    settings = build_settings()
    document_id = await repository.create("documento.pdf", "hash-1", None)

    await run_ingestion(
        document_id, documento(), REQUEST_ID, repository, build_embedder(settings), settings
    )

    do_pipeline = [
        entrada
        for entrada in captured_logs
        if entrada.get("event", "").startswith(("document.", "embedding."))
    ]
    assert do_pipeline
    assert all(entrada.get("document_id") == str(document_id) for entrada in do_pipeline)


async def test_falha_de_ingestao_tambem_e_rastreavel_pelo_request_id(
    repository: FakeRepository, captured_logs: list[dict[str, Any]]
) -> None:
    """O caminho de erro publica `document.failed` no mesmo `request_id`."""
    settings = build_settings()
    document_id = await repository.create("documento.pdf", "hash-1", None)
    quebrado = build_embedder(
        settings, failures=[errors.ClientError(400, {"error": {"message": "payload recusado"}})]
    )

    await run_ingestion(document_id, documento(), REQUEST_ID, repository, quebrado, settings)

    falhas = eventos(captured_logs, "document.failed")
    assert len(falhas) == 1
    assert falhas[0]["request_id"] == REQUEST_ID
    assert falhas[0]["document_id"] == str(document_id)
    assert repository.documents[document_id].status is DocumentStatus.FAILED


async def test_o_contexto_de_log_nao_vaza_para_a_proxima_ingestao(
    repository: FakeRepository, captured_logs: list[dict[str, Any]]
) -> None:
    """Cada ingestão limpa o contexto ao terminar; senão o log misturaria documentos."""
    settings = build_settings()
    primeiro = await repository.create("a.pdf", "hash-a", None)
    segundo = await repository.create("b.pdf", "hash-b", None)

    dados = documento()
    for identificador, request_id in ((primeiro, "req-a"), (segundo, "req-b")):
        await run_ingestion(
            identificador, dados, request_id, repository, build_embedder(settings), settings
        )

    por_documento = {
        entrada["request_id"]: entrada["document_id"]
        for entrada in eventos(captured_logs, "document.ready")
    }
    assert por_documento == {"req-a": str(primeiro), "req-b": str(segundo)}


# ─── AC-19: a chave nunca aparece no log ─────────────────────────────────────


@pytest.fixture(autouse=True)
def chave_no_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    """Define a `GEMINI_API_KEY` no ambiente do teste, como o AC-19 pressupõe.

    A suíte roda sem chave por decisão de projeto; o AC-19 só faz sentido com uma
    definida, então ela é injetada aqui — falsa, e apenas no processo do teste.
    """
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)


def erro_do_provedor(status: int) -> errors.ClientError:
    """Falha do provedor que ecoa a chave na mensagem, como acontece de verdade."""
    return errors.ClientError(status, {"error": {"message": f"falhou em ?key={FAKE_KEY}"}})


# Fábricas, e não instâncias prontas: uma exceção reaproveitada entre testes vai
# acumulando traceback, e o que se quer medir aqui é a saída de um caminho só.
CAMINHOS_DE_ERRO = [
    ("quota_esgotada", lambda: erro_do_provedor(429)),
    ("payload_recusado", lambda: erro_do_provedor(400)),
    ("erro_de_transporte", lambda: TimeoutError(f"falha ao chamar ?key={FAKE_KEY}")),
]


@pytest.mark.parametrize(("nome", "fabricar"), CAMINHOS_DE_ERRO)
async def test_a_chave_nao_aparece_no_log_em_nenhum_caminho_de_erro(
    repository: FakeRepository,
    captured_logs: list[dict[str, Any]],
    nome: str,
    fabricar: Callable[[], Exception],
) -> None:
    """AC-19: o provedor ecoa a chave na mensagem e ela é apagada antes do log."""
    settings = build_settings()
    document_id = await repository.create("documento.pdf", "hash-1", None)
    # Todas as tentativas falham: o caminho exercitado inclui o retry e a
    # desistência, que são justamente os que registram a mensagem do provedor.
    quebrado = build_embedder(settings, failures=[fabricar(), fabricar()])

    await run_ingestion(document_id, documento(), REQUEST_ID, repository, quebrado, settings)

    assert repository.documents[document_id].status is DocumentStatus.FAILED
    assert captured_logs
    assert FAKE_KEY not in texto_de(captured_logs), f"chave vazou no caminho {nome}"


@pytest.mark.parametrize(("nome", "fabricar"), CAMINHOS_DE_ERRO)
async def test_a_chave_nao_aparece_na_linha_de_log_renderizada(
    repository: FakeRepository,
    rendered_logs: io.StringIO,
    nome: str,
    fabricar: Callable[[], Exception],
) -> None:
    """AC-19 sobre a saída de verdade, que é onde o `grep` do avaliador roda.

    O `capture_logs` do teste acima enxerga o event dict antes da renderização e
    por isso é cego a traceback; este vê a linha completa, incluindo o
    `exception` que o `format_exc_info` acrescenta.
    """
    settings = build_settings()
    document_id = await repository.create("documento.pdf", "hash-1", None)
    quebrado = build_embedder(settings, failures=[fabricar(), fabricar()])

    await run_ingestion(document_id, documento(), REQUEST_ID, repository, quebrado, settings)

    saida = rendered_logs.getvalue()
    assert "document.failed" in saida
    assert FAKE_KEY not in saida, f"chave vazou na saída renderizada do caminho {nome}"


async def test_a_chave_nao_aparece_no_log_quando_a_ingestao_termina_bem(
    repository: FakeRepository, captured_logs: list[dict[str, Any]]
) -> None:
    """AC-19 no caminho feliz: nem o sucesso registra a credencial usada."""
    settings = build_settings()
    document_id = await repository.create("documento.pdf", "hash-1", None)

    await run_ingestion(
        document_id, documento(), REQUEST_ID, repository, build_embedder(settings), settings
    )

    assert repository.documents[document_id].status is DocumentStatus.READY
    assert FAKE_KEY not in texto_de(captured_logs)


async def test_a_chave_nao_aparece_na_mensagem_entregue_ao_usuario(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """AC-13 e AC-19: a mensagem que a tela exibe é em pt-BR e não cita a chave."""
    settings = build_settings()
    quebrado = build_embedder(settings, failures=[erro_do_provedor(429), erro_do_provedor(429)])

    async with build_client(embedding_client=quebrado, config=settings) as client:
        aceito = await client.post(
            "/api/documents",
            files={"file": ("documento.pdf", documento(), "application/pdf")},
        )
        corpo = (await client.get(f"/api/documents/{aceito.json()['id']}")).json()

    assert corpo["status"] == DocumentStatus.FAILED.value
    assert FAKE_KEY not in corpo["error_message"]
    assert "limite de uso" in corpo["error_message"].lower()


async def test_a_ausencia_de_chave_falha_sem_citar_configuracao_do_servidor(
    repository: FakeRepository, captured_logs: list[dict[str, Any]]
) -> None:
    """Sem chave, o adapter recusa antes de tentar a rede — e o log não a inventa."""
    settings = build_settings(gemini_api_key="")
    document_id = await repository.create("documento.pdf", "hash-1", None)
    sem_chave = GeminiEmbeddingClient(settings, sleep=lambda _seconds: None, max_attempts=1)

    await run_ingestion(document_id, documento(), REQUEST_ID, repository, sem_chave, settings)

    registro = repository.documents[document_id]
    assert registro.status is DocumentStatus.FAILED
    assert registro.error_message == MISSING_KEY_MESSAGE
    assert FAKE_KEY not in texto_de(captured_logs)
