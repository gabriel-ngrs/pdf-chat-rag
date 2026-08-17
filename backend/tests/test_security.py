"""As três propriedades de segurança da §4.8, provadas por comportamento.

A diferença entre este arquivo e uma afirmação em documento é que aqui o
segredo é realmente colocado no caminho do erro, o SQL malicioso é realmente
enviado ao Postgres e o nome de arquivo com travessia é realmente enviado à
rota. Um teste que só olha o código fonte provaria a leitura, não o sistema.

Três propriedades:

1. **A chave não aparece em log.** O pipeline inteiro roda com o renderizador
   JSON de produção e a saída é inspecionada byte a byte (AC-19).
2. **Todo SQL é parametrizado.** Contra o Postgres de verdade — sob o marker
   `db` —, com um payload que tenta derrubar a tabela `chunks`, e a prova é a
   tabela continuar de pé depois.
3. **Nome de arquivo é nome, não caminho.** `../../etc/passwd` é armazenado
   literalmente e nenhum byte é escrito fora do lugar.
"""

import io
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import structlog
from google.genai import errors

from app.adapters.db import Database
from app.adapters.gemini import GeminiEmbeddingClient
from app.adapters.repository import DocumentRecord, PostgresDocumentRepository
from app.api.documents import get_embedder, get_repository
from app.config import Settings, get_settings
from app.core.models import Chunk, DocumentStatus
from app.ingestion import run_ingestion
from app.logging_setup import MIN_SECRET_FRAGMENT, configure_logging
from app.main import create_app
from tests.factories import build_text_pdf

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_ENV_FILE = BACKEND_DIR.parent / ".env"

# Chave inventada, com o formato da real: o teste precisa de algo que pareça
# uma chave para que a sanitização por fragmento tenha o que reconhecer.
FAKE_KEY = "AIzaSyD-fake-key-para-teste-0123456789"

TRAVERSAL_FILENAME = "../../etc/passwd"

# Cada payload ataca um ponto diferente: fechar a string e emendar um comando,
# tornar o predicado sempre verdadeiro, e escapar por aspas duplas. O primeiro é
# destrutivo de propósito — é o que permite provar a defesa pela consequência.
SQL_PAYLOADS = (
    "'; DROP TABLE chunks; --",
    "' OR '1'='1",
    'x" OR 1=1 --',
    "\\'; DELETE FROM documents WHERE 1=1; --",
)


# ─── dublês ───────────────────────────────────────────────────────────────────


class RecordingRepository:
    """Repositório em memória que guarda exatamente o que a rota lhe entregou.

    Existe para que o teste de nome de arquivo afirme sobre o valor persistido,
    e não sobre o que a rota diz que persistiu.
    """

    def __init__(self) -> None:
        self.created: list[tuple[str, str, str | None]] = []
        self.records: dict[UUID, DocumentRecord] = {}

    async def create(self, filename: str, content_hash: str, session_id: str | None) -> UUID:
        self.created.append((filename, content_hash, session_id))
        document_id = uuid4()
        self.records[document_id] = DocumentRecord(
            id=document_id,
            filename=filename,
            status=DocumentStatus.PENDING,
            error_message=None,
            page_count=None,
            chunks_total=None,
            chunks_processed=0,
        )
        return document_id

    async def get(self, document_id: UUID) -> DocumentRecord | None:
        return self.records.get(document_id)

    async def find_by_hash(
        self, session_id: str | None, content_hash: str
    ) -> DocumentRecord | None:
        return None

    async def set_status(
        self, document_id: UUID, status: DocumentStatus, error_message: str | None = None
    ) -> None:
        record = self.records[document_id]
        self.records[document_id] = DocumentRecord(
            id=record.id,
            filename=record.filename,
            status=status,
            error_message=error_message,
            page_count=record.page_count,
            chunks_total=record.chunks_total,
            chunks_processed=record.chunks_processed,
        )

    async def set_totals(self, document_id: UUID, page_count: int, chunks_total: int) -> None:
        return None

    async def update_progress(self, document_id: UUID, chunks_processed: int) -> None:
        return None

    async def insert_chunks(
        self, document_id: UUID, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        return None

    async def reset_for_retry(self, document_id: UUID) -> None:
        return None

    async def sweep_orphans(self) -> int:
        return 0


class StubEmbedder:
    """Devolve vetores constantes: nenhum teste daqui exercita o provedor."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class LeakingModels:
    """Transporte falso que ecoa a chave em toda mensagem de erro.

    É o pior cenário realista: provedores devolvem a URL da requisição em texto
    de erro, e a URL pode levar a chave na query string.
    """

    def __init__(self, exception: Exception) -> None:
        self.exception = exception
        self.calls = 0

    def embed_content(self, **kwargs: Any) -> Any:
        self.calls += 1
        raise self.exception


class LeakingClient:
    def __init__(self, models: LeakingModels) -> None:
        self.models = models


def build_settings() -> Settings:
    """Settings isolada do `.env`, com a chave falsa e sem tocar o disco."""
    return Settings(
        _env_file=None,
        gemini_api_key=FAKE_KEY,
        embedding_batch_size=16,
        embedding_dim=768,
    )


@contextmanager
def logging_de_producao() -> Iterator[io.StringIO]:
    """Roda o bloco com o logging real e devolve tudo que foi escrito.

    O renderizador JSON de produção, e não o capturador de teste do structlog:
    o que interessa ao AC-19 são os bytes que chegariam ao arquivo de log,
    incluindo o traceback que o `format_exc_info` serializa.

    A configuração global é restaurada no fim para não contaminar o resto da
    suíte, que espera o nível e os processadores que já estavam valendo.
    """
    anterior = structlog.get_config()
    buffer = io.StringIO()
    configure_logging()
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        logger_factory=structlog.PrintLoggerFactory(file=buffer),
        cache_logger_on_first_use=False,
    )
    try:
        yield buffer
    finally:
        structlog.configure(**anterior)


def assert_sem_vazamento(texto: str) -> None:
    """Recusa a chave inteira e qualquer fragmento reconhecível dela.

    Meia chave em log já é vazamento: `MIN_SECRET_FRAGMENT` é o tamanho a partir
    do qual o adapter considera um trecho identificável, e a asserção usa o mesmo
    limiar para não ser mais frouxa que a defesa que verifica.
    """
    assert FAKE_KEY not in texto
    for start in range(len(FAKE_KEY) - MIN_SECRET_FRAGMENT + 1):
        fragmento = FAKE_KEY[start : start + MIN_SECRET_FRAGMENT]
        assert fragmento not in texto, f"fragmento da chave vazou: {fragmento}"


# ─── (a) AC-19: a chave não aparece em log em nenhum caminho de erro ──────────


@pytest.mark.parametrize(
    ("rotulo", "falha"),
    [
        (
            "400 do provedor ecoando a chave e a URL",
            errors.ClientError(
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
            ),
        ),
        (
            "429 repetido, exercitando o caminho de retry",
            errors.ClientError(
                429,
                {"error": {"message": f"quota exceeded for key {FAKE_KEY}", "status": "EXHAUSTED"}},
            ),
        ),
        (
            "500 do provedor, exercitando o caminho de esgotamento",
            errors.ServerError(
                500,
                {"error": {"message": f"internal error using {FAKE_KEY}", "status": "INTERNAL"}},
            ),
        ),
    ],
)
async def test_chave_nao_aparece_no_log_de_nenhum_caminho_de_erro(
    rotulo: str, falha: Exception
) -> None:
    """AC-19, ponta a ponta: pipeline real, logging real, saída inspecionada.

    Fora do módulo de logging de propósito. `test_logging.py` prova que o
    formatador não vaza; este prova que o sistema inteiro, rodando a ingestão de
    um PDF de verdade contra um provedor que ecoa a chave, também não.
    """
    settings = build_settings()
    repository = RecordingRepository()
    embedder = GeminiEmbeddingClient(
        settings,
        client=cast(Any, LeakingClient(LeakingModels(falha))),
        sleep=lambda _segundos: None,
        max_attempts=2,
    )
    document_id = await repository.create("documento.pdf", "hash", None)

    with logging_de_producao() as log:
        await run_ingestion(
            document_id,
            build_text_pdf(["Conteudo qualquer para haver o que embedar."]),
            "req-seguranca",
            cast(Any, repository),
            embedder,
            settings,
        )

    saida = log.getvalue()
    assert saida.strip(), f"{rotulo}: sem log nenhum o teste não prova nada"
    assert "document.failed" in saida, f"{rotulo}: o caminho de erro não foi exercitado"
    assert_sem_vazamento(saida)

    # O que o usuário vê também é superfície de vazamento.
    registro = repository.records[document_id]
    assert registro.status is DocumentStatus.FAILED
    assert registro.error_message is not None
    assert_sem_vazamento(registro.error_message)


async def test_chave_nao_vaza_por_excecao_inesperada_no_traceback() -> None:
    """Cobre a exceção que o adapter NÃO reconhece — o caminho que já vazou.

    `httpx.ReadTimeout` não é `TimeoutError` nem `OSError`, então escapa do
    `except` de `gemini._request`, chega ao catch-all de `run_ingestion` e vai
    parar no traceback que o `format_exc_info` serializa. Foi assim que a chave
    apareceu em log antes do processador de redação existir. Este teste é o que
    impede a regressão: ele falha se alguém tirar a redação da borda e voltar a
    confiar só na lista de exceções previstas do adapter.
    """
    settings = build_settings()
    repository = RecordingRepository()
    falha = httpx.ReadTimeout(f"timed out for https://api.exemplo/v1?key={FAKE_KEY}")
    embedder = GeminiEmbeddingClient(
        settings,
        client=cast(Any, LeakingClient(LeakingModels(falha))),
        sleep=lambda _segundos: None,
        max_attempts=1,
    )
    document_id = await repository.create("documento.pdf", "hash", None)

    with logging_de_producao() as log:
        await run_ingestion(
            document_id,
            build_text_pdf(["Conteudo qualquer."]),
            "req-seguranca",
            cast(Any, repository),
            embedder,
            settings,
        )

    assert_sem_vazamento(log.getvalue())


# ─── (b) SQL parametrizado, contra o Postgres de verdade ─────────────────────


def database_url() -> str:
    """DSN do ambiente, com o `.env` da raiz como segunda fonte.

    Variável de ambiente primeiro porque é como o CI e o compose injetam o valor;
    o `.env` cobre a execução manual a partir de `backend/`, onde ele não está no
    diretório corrente.
    """
    from_env = os.environ.get("DATABASE_URL")
    if from_env:
        return from_env
    env_file = str(ROOT_ENV_FILE) if ROOT_ENV_FILE.exists() else None
    return Settings(_env_file=env_file).database_url


@pytest.mark.db
async def test_find_by_hash_e_get_resistem_a_sql_injetado() -> None:
    """O payload tenta derrubar `chunks`; a prova é a tabela continuar existindo.

    Contra o banco real, e não contra um dublê: um dublê em memória aceitaria
    qualquer string e o teste provaria apenas que o dublê não interpreta SQL.
    Contar as linhas antes e depois é o que separa a prova da encenação — sem
    isso, um `DROP` bem-sucedido passaria despercebido, porque as consultas
    continuariam devolvendo `None` do mesmo jeito.
    """
    database = Database(database_url())
    await database.connect(timeout_seconds=10.0)
    repository = PostgresDocumentRepository(database)
    sessao = f"test-security-{uuid4()}"
    try:
        pool = database.pool
        chunks_antes = await pool.fetchval("SELECT count(*) FROM chunks")
        documentos_antes = await pool.fetchval("SELECT count(*) FROM documents")

        # 1. O payload como consulta: aspas, ponto e vírgula e `--` são dados.
        for payload in SQL_PAYLOADS:
            assert await repository.find_by_hash(payload, payload) is None
            assert await repository.find_by_hash(None, payload) is None
            assert await repository.find_by_hash(sessao, payload) is None

        # 2. O payload como dado gravado: entra e volta literal, sem interpretação.
        payload = SQL_PAYLOADS[0]
        document_id = await repository.create(payload, payload, sessao)
        encontrado = await repository.find_by_hash(sessao, payload)
        assert encontrado is not None
        assert encontrado.id == document_id
        assert encontrado.filename == payload

        lido = await repository.get(document_id)
        assert lido is not None and lido.filename == payload

        # 3. `get` recebe UUID: o driver recusa o payload antes de qualquer SQL,
        #    porque o valor é parâmetro tipado e não pedaço de query.
        for payload_id in SQL_PAYLOADS:
            with pytest.raises(asyncpg.DataError):
                await repository.get(cast(UUID, payload_id))

        # 4. O que separa a prova da encenação.
        assert await pool.fetchval("SELECT to_regclass('chunks')::text") == "chunks"
        assert await pool.fetchval("SELECT to_regclass('documents')::text") == "documents"
        assert await pool.fetchval("SELECT count(*) FROM chunks") == chunks_antes
        assert await pool.fetchval("SELECT count(*) FROM documents") == documentos_antes + 1
    finally:
        await database.pool.execute("DELETE FROM documents WHERE session_id = $1", sessao)
        await database.close()


# ─── (c) nome de arquivo é nome, nunca caminho ───────────────────────────────


def build_upload_client(
    repository: RecordingRepository,
) -> tuple[httpx.AsyncClient, Any]:
    """Monta o app com repositório e embedder em memória, sem lifespan nem banco."""
    settings = Settings(_env_file=None)
    application = create_app()
    application.dependency_overrides[get_repository] = lambda: repository
    application.dependency_overrides[get_embedder] = lambda: StubEmbedder()
    application.dependency_overrides[get_settings] = lambda: settings
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    )
    return client, application


async def test_filename_com_travessia_vira_nome_e_nao_caminho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`../../etc/passwd` é gravado como nome; nenhum byte sai do lugar.

    O diretório de trabalho é trocado por um vazio antes do envio para que
    qualquer escrita relativa apareça: se a rota (ou a task de background que ela
    agenda) tocasse o disco, o arquivo nasceria aqui e o teste veria. Provar que
    o nome foi guardado literal, sozinho, não bastaria — o valor de `basename`
    também seria literal em outro sentido, e um `open(filename, "wb")` em algum
    ponto do caminho continuaria invisível.
    """
    monkeypatch.chdir(tmp_path)
    passwd = Path("/etc/passwd")
    passwd_antes = passwd.read_bytes() if passwd.exists() else None

    repository = RecordingRepository()
    client, _ = build_upload_client(repository)
    async with client:
        response = await client.post(
            "/api/documents",
            files={
                "file": (
                    TRAVERSAL_FILENAME,
                    build_text_pdf(["Documento de teste."]),
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 202

    # 1. Armazenado como nome: literal, sem `basename`, sem normalização.
    assert len(repository.created) == 1
    filename, _hash, _sessao = repository.created[0]
    assert filename == TRAVERSAL_FILENAME

    # 2. E devolvido como nome, também literal — é dado, não caminho.
    document_id = UUID(response.json()["id"])
    async with build_upload_client(repository)[0] as leitor:
        detalhe = await leitor.get(f"/api/documents/{document_id}")
    assert detalhe.status_code == 200
    assert detalhe.json()["filename"] == TRAVERSAL_FILENAME

    # 3. Nada foi escrito: nem sob o diretório corrente, nem no alvo da travessia.
    assert list(tmp_path.rglob("*")) == []
    assert not (tmp_path / TRAVERSAL_FILENAME).exists()
    assert not (tmp_path.parent.parent / "etc" / "passwd").exists()

    # 4. E o alvo de verdade continua intacto.
    if passwd_antes is not None:
        assert passwd.read_bytes() == passwd_antes


@pytest.mark.parametrize(
    "nome",
    [
        "/etc/shadow",
        "..\\..\\windows\\system32\\config\\sam",
        "....//....//etc/passwd",
        "documento.pdf; rm -rf /",
        "$(cat /etc/passwd).pdf",
    ],
)
async def test_outros_nomes_maliciosos_tambem_ficam_como_nome(
    nome: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Travessia absoluta, travessia do Windows, dupla codificação e injeção de shell.

    Todas passam pelo mesmo ponto — `upload.filename` vira coluna `text` — e é
    por isso que a defesa não é uma lista de nomes proibidos: é o fato de o valor
    nunca ser interpretado como caminho nem como comando.
    """
    monkeypatch.chdir(tmp_path)
    repository = RecordingRepository()
    client, _ = build_upload_client(repository)
    async with client:
        response = await client.post(
            "/api/documents",
            files={"file": (nome, build_text_pdf(["Documento de teste."]), "application/pdf")},
        )

    assert response.status_code == 202
    assert repository.created[0][0] == nome
    assert list(tmp_path.rglob("*")) == []


