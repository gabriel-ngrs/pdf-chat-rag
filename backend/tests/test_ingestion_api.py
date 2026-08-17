"""Ingestão de ponta a ponta, com os dublês no lugar do banco e do provedor.

A divisão dos testes segue a divisão de responsabilidade do código. Pela rota é
verificado **o que a rota decide** — o `202`, as recusas por limite, o envelope
de erro e o desvio do reenvio duplicado. A máquina de estados é verificada
chamando `run_ingestion` diretamente, porque o `BackgroundTasks` do Starlette
termina antes de o cliente de teste devolver o POST: quando a resposta chega, a
ingestão já rodou inteira e a transição `pending → processing → ready` é
inobservável de fora.
"""

import asyncio
import itertools
import math
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from app.adapters.gemini import PROVIDER_MESSAGE, EmbeddingProviderError
from app.api.documents import NOT_PDF_MESSAGE
from app.config import Settings
from app.core.models import DocumentStatus
from app.ingestion import UNEXPECTED_MESSAGE, run_ingestion
from tests.factories import build_pdf_without_text_layer, build_text_pdf
from tests.fakes import FakeEmbeddingClient, FakeRepository

FAKE_KEY = "AIzaSyD-chave-falsa-para-teste-0123456789"
BOUNDARY = "----fronteira-de-teste-talkdoc"

PAGINA = (
    "O TalkDoc recebe um PDF, extrai o texto pagina a pagina e guarda cada "
    "trecho com o numero da pagina de origem. A citacao exata depende dessa "
    "fronteira ser respeitada do inicio ao fim do pipeline. "
)


def documento_de_tres_paginas() -> bytes:
    """PDF com texto suficiente para render mais de um chunk por página."""
    return build_text_pdf([f"Pagina {numero}. {PAGINA * 3}" for numero in (1, 2, 3)])


def upload_payload(data: bytes, filename: str = "documento.pdf") -> dict[str, Any]:
    return {"files": {"file": (filename, data, "application/pdf")}}


def multipart_body(data: bytes, filename: str = "documento.pdf") -> bytes:
    """Monta o corpo multipart à mão, para poder enviá-lo sem `Content-Length`."""
    cabecalho = (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    return cabecalho + data + f"\r\n--{BOUNDARY}--\r\n".encode()


async def stream_bytes(body: bytes, piece: int = 64 * 1024) -> AsyncIterator[bytes]:
    """Emite o corpo em pedaços, o que faz o httpx usar `Transfer-Encoding: chunked`."""
    for start in range(0, len(body), piece):
        yield body[start : start + piece]


async def enviar(client: httpx.AsyncClient, data: bytes, **kwargs: Any) -> httpx.Response:
    filename = kwargs.pop("filename", "documento.pdf")
    return await client.post("/api/documents", **upload_payload(data, filename), **kwargs)


async def estado(client: httpx.AsyncClient, document_id: Any) -> dict[str, Any]:
    response = await client.get(f"/api/documents/{document_id}")
    assert response.status_code == 200
    return dict(response.json())


# ─── O que a rota decide ─────────────────────────────────────────────────────


async def test_upload_de_pdf_valido_responde_202_pendente(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """AC-1: o aceite é imediato e anuncia `pending`, não o resultado final."""
    async with build_client() as client:
        response = await enviar(client, documento_de_tres_paginas())

    assert response.status_code == 202
    corpo = response.json()
    assert corpo["status"] == DocumentStatus.PENDING.value
    assert UUID(corpo["id"])


async def test_documento_processado_fica_ready_com_os_chunks_registrados(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    embedder: FakeEmbeddingClient,
) -> None:
    """AC-1 e AC-11 (na versão em memória): o fluxo termina com chunks gravados."""
    async with build_client() as client:
        aceito = await enviar(client, documento_de_tres_paginas())
        corpo = await estado(client, aceito.json()["id"])

    document_id = UUID(corpo["id"])
    assert corpo["status"] == DocumentStatus.READY.value
    assert corpo["page_count"] == 3
    assert corpo["chunks_total"] == corpo["chunks_processed"] > 0

    gravados = repository.chunks[document_id]
    assert len(gravados) == corpo["chunks_total"]
    assert [chunk.chunk_index for chunk, _ in gravados] == list(range(len(gravados)))
    assert {chunk.page_number for chunk, _ in gravados} == {1, 2, 3}
    for _, embedding in gravados:
        assert len(embedding) == embedder.dim
        assert math.isclose(math.sqrt(sum(v * v for v in embedding)), 1.0, rel_tol=1e-9)


async def test_um_chunk_nunca_mistura_duas_paginas(
    build_client: Callable[..., httpx.AsyncClient], repository: FakeRepository
) -> None:
    """Cada chunk gravado cita a página em que seu texto realmente aparece.

    Cada página do PDF começa com o marcador `Pagina N.`; se um chunk carregasse
    o marcador de uma página diferente da sua, a citação apontaria para o lugar
    errado no documento.
    """
    async with build_client() as client:
        aceito = await enviar(client, documento_de_tres_paginas())

    document_id = UUID(aceito.json()["id"])
    for chunk, _ in repository.chunks[document_id]:
        marcadores = {numero for numero in (1, 2, 3) if f"Pagina {numero}." in chunk.content}
        assert marcadores <= {chunk.page_number}


async def test_arquivo_acima_do_limite_declarado_recebe_413(
    build_client: Callable[..., httpx.AsyncClient], settings: Settings
) -> None:
    """AC-2: o corpo da recusa é o envelope JSON do projeto, não HTML de proxy."""
    gordo = b"%PDF" + b"0" * (settings.max_upload_bytes + 1)

    async with build_client() as client:
        response = await enviar(client, gordo)

    assert response.status_code == 413
    assert response.json() == {
        "code": "arquivo_grande",
        "message": f"O arquivo excede o limite de {settings.max_upload_mb} MB.",
    }


async def test_arquivo_acima_do_limite_sem_content_length_recebe_413(
    build_client: Callable[..., httpx.AsyncClient], settings: Settings
) -> None:
    """AC-2 pelo outro caminho: sem `Content-Length`, o corte acontece na leitura.

    O tamanho declarado vem do cliente e pode mentir; este teste prova que o
    limite continua valendo quando ele simplesmente não é declarado.
    """
    corpo = multipart_body(b"%PDF" + b"0" * (settings.max_upload_bytes + 1))

    async with build_client() as client:
        response = await client.post(
            "/api/documents",
            content=stream_bytes(corpo),
            headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
        )

    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert response.json()["code"] == "arquivo_grande"


async def test_txt_renomeado_para_pdf_recebe_422(
    build_client: Callable[..., httpx.AsyncClient], repository: FakeRepository
) -> None:
    """AC-3: a assinatura do arquivo manda mais que a extensão do nome."""
    async with build_client() as client:
        response = await enviar(client, b"Isto aqui e um texto puro.\n", filename="disfarce.pdf")

    assert response.status_code == 422
    assert response.json() == {"code": "arquivo_invalido", "message": NOT_PDF_MESSAGE}
    assert repository.documents == {}


async def test_requisicao_sem_campo_file_recebe_422(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """AC-3 e AC-17: formulário sem o campo esperado também sai no envelope."""
    async with build_client() as client:
        response = await client.post("/api/documents", data={"outro": "campo"})

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "arquivo_invalido"


async def test_documento_inexistente_responde_404_no_envelope(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """AC-17: o 404 usa o mesmo envelope `{code, message}` das demais falhas."""
    async with build_client() as client:
        response = await client.get(f"/api/documents/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"code": "nao_encontrado", "message": "Documento não encontrado."}


async def test_id_malformado_sai_no_envelope_de_validacao(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """AC-17: nem o erro de validação do framework escapa do envelope."""
    async with build_client() as client:
        response = await client.get("/api/documents/isto-nao-e-uuid")

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "arquivo_invalido"


async def test_pdf_acima_do_limite_de_paginas_termina_failed(
    build_client: Callable[..., httpx.AsyncClient], settings: Settings
) -> None:
    """AC-4: o limite de páginas só é conhecido no parse, então vira `failed`."""
    excedente = settings.max_pdf_pages + 1
    grande = build_text_pdf([f"Pagina {numero}." for numero in range(1, excedente + 1)])

    async with build_client() as client:
        aceito = await enviar(client, grande)
        corpo = await estado(client, aceito.json()["id"])

    assert corpo["status"] == DocumentStatus.FAILED.value
    assert str(settings.max_pdf_pages) in corpo["error_message"]
    assert str(excedente) in corpo["error_message"]


async def test_pdf_sem_camada_de_texto_termina_failed(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """AC-5: documento escaneado falha explicando que OCR não é suportado."""
    async with build_client() as client:
        aceito = await enviar(client, build_pdf_without_text_layer(2))
        corpo = await estado(client, aceito.json()["id"])

    assert corpo["status"] == DocumentStatus.FAILED.value
    assert "OCR" in corpo["error_message"]


async def test_falha_permanente_do_provedor_termina_failed_sem_vazar_chave(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """AC-13: a mensagem exibida é em pt-BR e não carrega credencial nenhuma."""
    config = Settings(_env_file=None, gemini_api_key=FAKE_KEY, chunk_size=200, chunk_overlap=40)
    quebrado = FakeEmbeddingClient(error=EmbeddingProviderError(PROVIDER_MESSAGE))

    async with build_client(embedding_client=quebrado, config=config) as client:
        aceito = await enviar(client, documento_de_tres_paginas())
        corpo = await estado(client, aceito.json()["id"])

    assert corpo["status"] == DocumentStatus.FAILED.value
    assert corpo["error_message"] == PROVIDER_MESSAGE
    assert FAKE_KEY not in corpo["error_message"]


async def test_falha_inesperada_nao_deixa_o_documento_em_processing(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """Nenhum caminho de saída pode parar em `processing` — seria barra eterna."""
    cru = FakeEmbeddingClient(error=RuntimeError("estouro que o pipeline não previu"))

    async with build_client(embedding_client=cru) as client:
        aceito = await enviar(client, documento_de_tres_paginas())
        corpo = await estado(client, aceito.json()["id"])

    assert corpo["status"] == DocumentStatus.FAILED.value
    assert corpo["error_message"] == UNEXPECTED_MESSAGE


async def test_reenvio_identico_na_mesma_sessao_nao_reprocessa(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    embedder: FakeEmbeddingClient,
) -> None:
    """AC-15: o segundo envio devolve o documento existente e não gasta quota."""
    data = documento_de_tres_paginas()
    cabecalho = {"X-Session-Id": "sessao-do-teste"}

    async with build_client() as client:
        primeiro = await enviar(client, data, headers=cabecalho)
        lotes_apos_o_primeiro = len(embedder.batches)
        segundo = await enviar(client, data, headers=cabecalho)

    assert segundo.status_code == 202
    assert segundo.json()["id"] == primeiro.json()["id"]
    assert segundo.json()["status"] == DocumentStatus.READY.value
    assert len(embedder.batches) == lotes_apos_o_primeiro
    assert len(repository.documents) == 1


async def test_mesmo_pdf_em_outra_sessao_gera_documento_proprio(
    build_client: Callable[..., httpx.AsyncClient], repository: FakeRepository
) -> None:
    """AC-15 pela borda: a deduplicação é por sessão, não global."""
    data = documento_de_tres_paginas()

    async with build_client() as client:
        primeiro = await enviar(client, data, headers={"X-Session-Id": "sessao-a"})
        segundo = await enviar(client, data, headers={"X-Session-Id": "sessao-b"})

    assert primeiro.json()["id"] != segundo.json()["id"]
    assert len(repository.documents) == 2


# ─── O que o pipeline decide ─────────────────────────────────────────────────


async def test_pipeline_percorre_pending_processing_e_ready(
    repository: FakeRepository, embedder: FakeEmbeddingClient, settings: Settings
) -> None:
    """AC-12: a transição existe, mesmo sendo invisível de fora da rota."""
    document_id = await repository.create("documento.pdf", "hash-1", None)
    assert repository.documents[document_id].status is DocumentStatus.PENDING

    await run_ingestion(
        document_id, documento_de_tres_paginas(), "req-1", repository, embedder, settings
    )

    assert repository.statuses_of(document_id) == [
        DocumentStatus.PROCESSING,
        DocumentStatus.READY,
    ]


async def test_progresso_cresce_monotonicamente_ate_o_total(
    repository: FakeRepository, embedder: FakeEmbeddingClient, settings: Settings
) -> None:
    """AC-12: o progresso é publicado por lote e nunca anda para trás."""
    document_id = await repository.create("documento.pdf", "hash-1", None)

    await run_ingestion(
        document_id, documento_de_tres_paginas(), "req-1", repository, embedder, settings
    )

    progresso = repository.progress_of(document_id)
    total = repository.documents[document_id].chunks_total
    assert len(progresso) > 1
    assert progresso == sorted(progresso)
    assert len(set(progresso)) == len(progresso)
    assert progresso[-1] == total


async def test_progresso_nao_avanca_alem_do_ponto_da_falha(
    repository: FakeRepository, settings: Settings
) -> None:
    """Falha no meio do embedding: o progresso para onde parou e o estado é `failed`."""
    document_id = await repository.create("documento.pdf", "hash-1", None)
    quebrado = FakeEmbeddingClient(error=EmbeddingProviderError(PROVIDER_MESSAGE))

    await run_ingestion(
        document_id, documento_de_tres_paginas(), "req-1", repository, quebrado, settings
    )

    assert repository.progress_of(document_id) == []
    assert repository.statuses_of(document_id)[-1] is DocumentStatus.FAILED
    assert document_id not in repository.chunks


async def test_dois_pipelines_concorrentes_nao_se_intercalam(
    repository: FakeRepository, embedder: FakeEmbeddingClient, settings: Settings
) -> None:
    """AC-28: o semáforo global serializa a ingestão inteira, não só um trecho.

    A prova é a ordem das chamadas registradas no repositório: se as duas
    ingestões tivessem rodado entrelaçadas, a sequência de documentos alternaria
    e teria mais de dois blocos contíguos.
    """
    data = documento_de_tres_paginas()
    primeiro = await repository.create("a.pdf", "hash-a", None)
    segundo = await repository.create("b.pdf", "hash-b", None)
    repository.operations.clear()

    await asyncio.gather(
        run_ingestion(primeiro, data, "req-a", repository, embedder, settings),
        run_ingestion(segundo, data, "req-b", repository, embedder, settings),
    )

    ordem = [document_id for _, document_id in repository.operations]
    blocos = [document_id for document_id, _ in itertools.groupby(ordem)]
    assert blocos in ([primeiro, segundo], [segundo, primeiro])
    assert repository.documents[primeiro].status is DocumentStatus.READY
    assert repository.documents[segundo].status is DocumentStatus.READY


async def test_semaforo_serializa_mesmo_quando_a_primeira_ingestao_falha(
    repository: FakeRepository, settings: Settings
) -> None:
    """O semáforo é liberado no caminho de erro; senão a fila travaria para sempre."""
    data = documento_de_tres_paginas()
    quebrado = FakeEmbeddingClient(error=EmbeddingProviderError(PROVIDER_MESSAGE))
    saudavel = FakeEmbeddingClient()
    primeiro = await repository.create("a.pdf", "hash-a", None)
    segundo = await repository.create("b.pdf", "hash-b", None)

    await run_ingestion(primeiro, data, "req-a", repository, quebrado, settings)
    await run_ingestion(segundo, data, "req-b", repository, saudavel, settings)

    assert repository.documents[primeiro].status is DocumentStatus.FAILED
    assert repository.documents[segundo].status is DocumentStatus.READY


@pytest.mark.parametrize("lote", [1, 2, 100])
async def test_o_total_embedado_independe_do_tamanho_do_lote(
    repository: FakeRepository, embedder: FakeEmbeddingClient, lote: int
) -> None:
    """O lote é detalhe de quota: o conjunto de chunks gravados não muda com ele."""
    config = Settings(
        _env_file=None, chunk_size=200, chunk_overlap=40, embedding_batch_size=lote
    )
    document_id = await repository.create("documento.pdf", "hash-1", None)

    await run_ingestion(
        document_id, documento_de_tres_paginas(), "req-1", repository, embedder, config
    )

    gravados = repository.chunks[document_id]
    assert len(embedder.embedded_texts) == len(gravados)
    assert embedder.embedded_texts == [chunk.content for chunk, _ in gravados]


# ─── Regressão da avaliação da A.4 (I-1) e da A.2 (I-1, guarda simétrico) ────


class FalhaUmaVezDepoisFunciona(FakeEmbeddingClient):
    """Provedor que falha no primeiro documento e funciona do segundo em diante.

    Reproduz o cenário real que a avaliação apontou: uma oscilação de rede
    derruba a primeira ingestão, e o usuário faz o que a mensagem manda —
    envia de novo.
    """

    def __init__(self) -> None:
        super().__init__()
        self.deve_falhar = True

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.deve_falhar:
            self.deve_falhar = False
            self.batches.append(list(texts))
            raise EmbeddingProviderError(PROVIDER_MESSAGE)
        return super().embed_documents(texts)


async def test_documento_que_falhou_e_reprocessado_no_reenvio(
    build_client: Callable[..., httpx.AsyncClient], repository: FakeRepository
) -> None:
    """O reenvio de um documento `failed` reprocessa, em vez de devolver a falha.

    Antes da correção o dedup por hash não olhava o `status`: o segundo envio
    devolvia o mesmo registro falho, e como a chave é `(session_id, hash)` e o
    `session_id` vive no `localStorage`, a única saída do usuário era limpar o
    navegador. O sistema instruía uma ação que ele próprio impedia.
    """
    provedor = FalhaUmaVezDepoisFunciona()
    data = documento_de_tres_paginas()
    cabecalho = {"X-Session-Id": "sessao-do-teste"}

    async with build_client(embedding_client=provedor) as client:
        primeiro = await enviar(client, data, headers=cabecalho)
        apos_falha = await estado(client, primeiro.json()["id"])

        segundo = await enviar(client, data, headers=cabecalho)
        apos_reenvio = await estado(client, segundo.json()["id"])

    assert apos_falha["status"] == DocumentStatus.FAILED.value
    assert segundo.json()["id"] == primeiro.json()["id"]
    assert apos_reenvio["status"] == DocumentStatus.READY.value
    assert apos_reenvio["error_message"] is None
    assert apos_reenvio["chunks_total"] == apos_reenvio["chunks_processed"]
    assert len(repository.documents) == 1
    assert repository.retries == [UUID(primeiro.json()["id"])]


async def test_reenvio_de_documento_pronto_continua_sem_reprocessar(
    build_client: Callable[..., httpx.AsyncClient], embedder: FakeEmbeddingClient
) -> None:
    """A correção do reenvio não pode desfazer o dedup do AC-15.

    Só o estado `failed` volta a processar; `ready` continua sendo devolvido de
    graça, que é o que protege a quota.
    """
    data = documento_de_tres_paginas()
    cabecalho = {"X-Session-Id": "sessao-do-teste"}

    async with build_client() as client:
        primeiro = await enviar(client, data, headers=cabecalho)
        lotes = len(embedder.batches)
        segundo = await enviar(client, data, headers=cabecalho)

    assert segundo.json()["id"] == primeiro.json()["id"]
    assert segundo.json()["status"] == DocumentStatus.READY.value
    assert len(embedder.batches) == lotes


async def test_documento_sem_chunk_nenhum_nao_termina_ready(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """Guarda simétrico ao de `extract_pages`: zero chunks é falha, não sucesso.

    Um PDF cuja camada de texto é só espaço chegava a `ready` com
    `chunks_total: 0`, e na FEAT-0002 toda pergunta receberia "não encontrei
    isso no documento" — o diagnóstico errado, porque o problema é o documento.
    """
    async with build_client() as client:
        aceito = await enviar(client, build_text_pdf(["   ", "  \t "]))
        corpo = await estado(client, aceito.json()["id"])

    assert corpo["status"] == DocumentStatus.FAILED.value
    assert "OCR" in corpo["error_message"]


async def test_chunking_vazio_termina_failed_mesmo_com_texto_extraido(
    repository: FakeRepository,
    embedder: FakeEmbeddingClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O guarda de zero chunks protege contra divergência entre duas noções de "vazio".

    O adapter decide por `str.strip()` e o núcleo por `normalize_whitespace`.
    Hoje as duas concordam, e por isso **nenhum PDF real alcança este guarda** —
    medi isso: a suíte inteira passa sem ele. O teste força a condição em vez de
    fingir um PDF que a produza, para que o guarda seja verificado de verdade e
    não fique como código decorativo.
    """
    monkeypatch.setattr("app.ingestion.chunk_pages", lambda *args, **kwargs: [])
    document_id = await repository.create("documento.pdf", "hash-sem-chunk", None)

    await run_ingestion(
        document_id, documento_de_tres_paginas(), "req-sem-chunk", repository, embedder, settings
    )

    registro = repository.documents[document_id]
    assert registro.status is DocumentStatus.FAILED
    assert "OCR" in (registro.error_message or "")
    assert embedder.batches == []
