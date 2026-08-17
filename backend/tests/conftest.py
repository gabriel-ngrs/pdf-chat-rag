"""Fixtures compartilhadas da suíte: dublês injetados e captura de log.

O ponto de injeção é `app.dependency_overrides`, e não monkeypatch de módulo,
porque é exatamente o mecanismo que `get_repository`/`get_embedder` existem para
servir — testar por outro caminho provaria menos do que o código promete.

O cliente HTTP é montado com `httpx.ASGITransport`, como já faz `test_health.py`.
Ele **não dispara o lifespan**, o que é a razão de nenhum teste offline abrir
conexão com o Postgres: o pool só nasce lá dentro.
"""

import asyncio
import io
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
import structlog
from fastapi import FastAPI
from structlog.testing import capture_logs

from app import ingestion
from app.adapters.gemini import ChatClient, EmbeddingClient
from app.adapters.repository import ConversationRepository, DocumentRepository
from app.api.conversations import get_chat_client, get_conversation_repository
from app.api.documents import get_embedder, get_repository
from app.config import Settings, get_settings
from app.logging_setup import clear_request_context, configure_logging
from app.main import create_app
from tests.fakes import (
    FakeChatClient,
    FakeConversationRepository,
    FakeEmbeddingClient,
    FakeRepository,
)

BASE_URL = "http://testserver"


def pytest_configure(config: pytest.Config) -> None:
    """Suspende o piso de cobertura quando a seleção é só a suíte de banco.

    `addopts` vale para toda invocação do pytest, e `make test-db` roda apenas os
    testes marcados `db`, que não exercitam `core/`. Sem esta suspensão o comando
    falharia por um número que não fala sobre ele — e o reflexo seria baixar o
    `--cov-fail-under`, que é justamente o que a fase proíbe. O piso continua
    valendo integralmente em `make test`, que é onde ele é gate.

    O piso é apagado no namespace do próprio plugin de cobertura, e não em
    `config.option`: o `pytest-cov` guarda o seu (`known_args_namespace`) já em
    `pytest_load_initial_conftests`, e é dele que o valor é lido na hora de
    reportar — mexer no outro não teria efeito nenhum.
    """
    if getattr(config.option, "markexpr", "") != "db":
        return
    plugin = config.pluginmanager.get_plugin("_cov")
    if plugin is not None:
        plugin.options.cov_fail_under = 0


@pytest.fixture(autouse=True)
def contexto_de_log_limpo() -> Iterator[None]:
    """Zera o contexto do structlog em volta de cada teste.

    `request_id` e `document_id` moram em contextvars de processo; um teste que
    falhasse no meio deixaria os dois amarrados e o próximo veria log alheio.
    """
    clear_request_context()
    yield
    clear_request_context()


@pytest.fixture(autouse=True)
def semaforo_de_pipeline_novo() -> Iterator[None]:
    """Devolve à ingestão um semáforo novo a cada teste.

    `_pipeline_lock` nasce no import do módulo, e um `asyncio.Semaphore` se
    prende ao primeiro event loop em que houver disputa. Como cada teste roda num
    loop próprio, sem esta troca o segundo teste concorrente morreria com "bound
    to a different event loop" — falha de infraestrutura de teste, não de
    comportamento, e do tipo que depende da ordem de execução.
    """
    ingestion._pipeline_lock = asyncio.Semaphore(1)
    yield


@pytest.fixture
def settings() -> Settings:
    """Configuração do processo com limites apertados, para o teste ser barato.

    `_env_file=None` é obrigatório: sem isso um `.env` presente na máquina de
    quem roda a suíte mudaria os limites e o resultado do teste.
    """
    return Settings(
        _env_file=None,
        gemini_api_key="",
        embedding_dim=8,
        max_upload_mb=1,
        max_pdf_pages=5,
        max_extracted_chars=20_000,
        chunk_size=200,
        chunk_overlap=40,
        embedding_batch_size=2,
    )


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def embedder() -> FakeEmbeddingClient:
    return FakeEmbeddingClient()


@pytest.fixture
def journal() -> list[str]:
    """Linha do tempo única compartilhada pelos dublês do chat.

    A ordem que FR-9 promete — pergunta gravada **antes** de qualquer chamada ao
    provedor — atravessa dois colaboradores, e cada um deles só enxerga as
    próprias chamadas. Um diário compartilhado é o que torna a ordem entre eles
    verificável por asserção.
    """
    return []


@pytest.fixture
def conversations(journal: list[str]) -> FakeConversationRepository:
    return FakeConversationRepository(journal=journal)


@pytest.fixture
def chat_client(journal: list[str]) -> FakeChatClient:
    return FakeChatClient(journal=journal)


@pytest.fixture
def build_app(
    repository: FakeRepository,
    embedder: FakeEmbeddingClient,
    settings: Settings,
    conversations: FakeConversationRepository,
    chat_client: FakeChatClient,
) -> Callable[..., FastAPI]:
    """Fábrica de app com os dublês no lugar das dependências de infraestrutura."""

    def make(
        *,
        repo: DocumentRepository | None = None,
        embedding_client: EmbeddingClient | None = None,
        config: Settings | None = None,
        conversation_repo: ConversationRepository | None = None,
        chat: ChatClient | None = None,
    ) -> FastAPI:
        app = create_app()
        app.dependency_overrides[get_repository] = lambda: repo if repo is not None else repository
        app.dependency_overrides[get_embedder] = (
            lambda: embedding_client if embedding_client is not None else embedder
        )
        app.dependency_overrides[get_settings] = lambda: config if config is not None else settings
        app.dependency_overrides[get_conversation_repository] = (
            lambda: conversation_repo if conversation_repo is not None else conversations
        )
        app.dependency_overrides[get_chat_client] = (
            lambda: chat if chat is not None else chat_client
        )
        return app

    return make


@pytest.fixture
def build_client(build_app: Callable[..., FastAPI]) -> Callable[..., httpx.AsyncClient]:
    """Fábrica de cliente HTTP sobre o app já com os dublês injetados."""

    def make(**kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=build_app(**kwargs)), base_url=BASE_URL
        )

    return make


@pytest.fixture
def captured_logs() -> Iterator[list[dict[str, Any]]]:
    """Entrega a lista de eventos que o structlog emitir durante o teste.

    `structlog.testing.capture_logs` foi escolhido em vez de redirecionar a saída
    do `PrintLoggerFactory`: ele entrega o **event dict** antes da renderização,
    então a asserção é sobre os campos (`event`, `request_id`, `duration_ms`) e
    não sobre uma string de JSON, e não depende do formato do renderer.

    Duas correções são necessárias sobre o comportamento padrão dele:

    * `configure_logging()` é chamado antes porque `capture_logs` preserva o
      `wrapper_class` já configurado — e é ele que decide o nível mínimo. Sem a
      configuração da aplicação (que filtra em debug) o evento `embedding.batch`,
      catalogado como debug em §4.4, seria descartado antes de ser capturado.
    * `merge_contextvars` é reinjetado como processador porque `capture_logs`
      limpa a cadeia inteira; sem ele, `request_id` e `document_id` sumiriam do
      dict capturado e o AC-18 ficaria impossível de verificar.
    """
    previous = structlog.get_config()
    configure_logging()
    try:
        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as entries:
            yield entries
    finally:
        structlog.configure(**previous)


@pytest.fixture
def rendered_logs() -> Iterator[io.StringIO]:
    """Entrega a saída do structlog já renderizada, como ela sai no stdout.

    Complementa `captured_logs` em vez de substituí-lo, e a diferença importa
    para o AC-19: `capture_logs` entrega o event dict **antes** do
    `format_exc_info`, então um traceback nunca aparece nele — e traceback é
    exatamente onde uma credencial vazaria sem ninguém ver. Aqui a asserção é
    sobre a linha de JSON inteira, tal como ela seria gravada.

    O desvio é feito trocando o `logger_factory`, e não redirecionando o
    `sys.stdout` do processo: o pytest reatribui o `sys.stdout` a cada fase do
    teste, então um `redirect_stdout` montado no setup da fixture já não estaria
    valendo quando o teste rodasse. A cadeia de processadores continua sendo a
    da aplicação, que é o que dá valor à asserção.
    """
    previous = structlog.get_config()
    configure_logging()
    buffer = io.StringIO()
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=buffer))
    try:
        yield buffer
    finally:
        structlog.configure(**previous)
