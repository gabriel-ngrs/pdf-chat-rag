"""Persistência de documentos, chunks, conversas e mensagens.

Todo SQL é escrito à mão e parametrizado — não existe ORM nem query builder no
projeto, e nenhuma string de SQL é montada por concatenação com entrada externa.

Os protocolos `DocumentRepository` e `ConversationRepository` existem para que a
suíte offline substitua o banco por um dublê em memória: são eles que tornam
`make check` executável na máquina de quem clona o projeto, sem Postgres no ar.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.adapters.db import Database
from app.core.models import Chunk, Citation, DocumentStatus, Message, MessageRole, RetrievedChunk
from app.core.retrieval import similarity_from_distance
from app.errors import InternalError

_CREATE_SQL = """
    INSERT INTO documents (filename, content_hash, status, session_id)
         VALUES ($1, $2, $3, $4)
      RETURNING id
"""

_GET_SQL = """
    SELECT id, filename, status, error_message, page_count,
           chunks_total, chunks_processed
      FROM documents
     WHERE id = $1
"""

_FIND_BY_HASH_SQL = """
    SELECT id, filename, status, error_message, page_count,
           chunks_total, chunks_processed
      FROM documents
     WHERE session_id IS NOT DISTINCT FROM $1
       AND content_hash = $2
"""

_SET_STATUS_SQL = """
    UPDATE documents
       SET status = $2,
           error_message = $3
     WHERE id = $1
"""

_SET_TOTALS_SQL = """
    UPDATE documents
       SET page_count = $2,
           chunks_total = $3
     WHERE id = $1
"""

_UPDATE_PROGRESS_SQL = """
    UPDATE documents
       SET chunks_processed = $2
     WHERE id = $1
"""

_INSERT_CHUNK_SQL = """
    INSERT INTO chunks (document_id, chunk_index, page_number, content, embedding)
         VALUES ($1, $2, $3, $4, $5::vector)
"""

_RESET_FOR_RETRY_SQL = """
    UPDATE documents
       SET status = $2,
           error_message = NULL,
           page_count = NULL,
           chunks_total = NULL,
           chunks_processed = 0
     WHERE id = $1
"""

_DELETE_CHUNKS_SQL = "DELETE FROM chunks WHERE document_id = $1"

_CREATE_CONVERSATION_SQL = """
    INSERT INTO conversations (document_id, session_id)
         VALUES ($1, $2)
      RETURNING id
"""

_GET_CONVERSATION_SQL = """
    SELECT id, document_id, session_id, created_at
      FROM conversations
     WHERE id = $1
"""

# O `RETURNING` traz a linha inteira porque `id`, `citations` e `created_at` são
# gerados ou normalizados pelo banco: reler com um SELECT depois seria uma
# segunda viagem para descobrir o que o INSERT já sabia.
_ADD_MESSAGE_SQL = """
    INSERT INTO messages (conversation_id, role, content, citations, truncated)
         VALUES ($1, $2, $3, $4::jsonb, $5)
      RETURNING id, role, content, citations, truncated, created_at
"""

# O desempate por `id` não é preciosismo: `created_at` tem default `now()`, que
# é o instante da transação, e duas mensagens gravadas no mesmo instante sairiam
# em ordem arbitrária — trocando pergunta e resposta no histórico.
_LIST_MESSAGES_SQL = """
    SELECT id, role, content, citations, truncated, created_at
      FROM messages
     WHERE conversation_id = $1
     ORDER BY created_at, id
"""

# O `<=>` é obrigatório e não é preferência de estilo: o índice de `001_init.sql`
# é `hnsw (embedding vector_cosine_ops)`, e qualquer outro operador de distância
# o ignora em silêncio — a busca continua devolvendo o resultado certo, só que
# varrendo a tabela inteira, sem nenhum erro que denuncie a troca.
#
# O filtro por `document_id` vem antes de tudo na leitura desta query porque é
# ele que sustenta o AC-6: a conversa é sobre um documento, e um chunk vizinho
# vindo de outro PDF produziria uma citação apontando para um arquivo que o
# usuário nem tem aberto.
_SEARCH_CHUNKS_SQL = """
    SELECT chunk_index, page_number, content, embedding <=> $2::vector AS distance
      FROM chunks
     WHERE document_id = $1
     ORDER BY embedding <=> $2::vector
     LIMIT $3
"""

# Sem isto, a busca **devolve menos linhas do que o `LIMIT` pede** — e a falha é
# silenciosa. Num `Index Scan` sobre HNSW o pgvector entrega os vizinhos
# **globais** mais próximos (até `ef_search`) e só então o `WHERE document_id`
# descarta o que veio de outro documento; com a varredura iterativa desligada,
# que é o default do pgvector 0.8, o que foi descartado não é reposto. O efeito
# no produto é o pior possível: `has_grounding` dá falso e o turno vira recusa
# numa pergunta que o documento responde, sem erro nem log anômalo.
#
# `relaxed_order` e não `strict_order` porque o pipeline reordena por score em
# `core.retrieval.take_top_k`: pagar pela ordenação estrita no banco seria pagar
# duas vezes pela mesma garantia.
#
# É `SET LOCAL`, então vale só dentro da transação e não vaza para as outras
# consultas que compartilham a conexão do pool. O valor é constante literal —
# GUC não aceita placeholder, e nada aqui vem de entrada externa.
_ITERATIVE_SCAN_SQL = "SET LOCAL hnsw.iterative_scan = relaxed_order"


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """Estado de um documento como a API o publica."""

    id: UUID
    filename: str
    status: DocumentStatus
    error_message: str | None
    page_count: int | None
    chunks_total: int | None
    chunks_processed: int


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    """Estado de uma conversa: a quem ela pertence e a que documento se prende.

    `document_id` é o que amarra o retrieval ao documento certo — sem ele, a
    rota teria de confiar num id vindo do cliente para decidir onde buscar, e o
    isolamento entre documentos (AC-6) deixaria de ser garantia do servidor.
    """

    id: UUID
    document_id: UUID
    session_id: str | None
    created_at: datetime


class DocumentRepository(Protocol):
    """O que o pipeline de ingestão e as rotas precisam do armazenamento."""

    async def create(self, filename: str, content_hash: str, session_id: str | None) -> UUID: ...

    async def get(self, document_id: UUID) -> DocumentRecord | None: ...

    async def find_by_hash(
        self, session_id: str | None, content_hash: str
    ) -> DocumentRecord | None: ...

    async def set_status(
        self, document_id: UUID, status: DocumentStatus, error_message: str | None = None
    ) -> None: ...

    async def set_totals(self, document_id: UUID, page_count: int, chunks_total: int) -> None: ...

    async def update_progress(self, document_id: UUID, chunks_processed: int) -> None: ...

    async def insert_chunks(
        self, document_id: UUID, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None: ...

    async def reset_for_retry(self, document_id: UUID) -> None: ...

    async def sweep_orphans(self) -> int: ...


class ConversationRepository(Protocol):
    """O que o chat precisa do armazenamento de conversas e mensagens.

    Protocolo separado de `DocumentRepository`, e não métodos acrescentados a
    ele, por duas razões práticas. A rota de chat da fase A.4 injeta só isto —
    declarar a dependência pelo protocolo estreito diz na assinatura que ela não
    mexe no ciclo de vida de documento. E o dublê da suíte offline (`fakes.py`)
    implementa `DocumentRepository`: engordar aquele protocolo obrigaria todo
    teste de ingestão a arrastar métodos de conversa que não usa.

    A busca vetorial entra aqui, e não num terceiro protocolo, porque ela é um
    passo do turno de chat como os outros: quem persiste a pergunta é quem
    recupera os trechos e quem grava a resposta. Separá-la só produziria duas
    dependências que sempre viajam juntas e sempre apontam para o mesmo objeto.
    """

    async def create_conversation(self, document_id: UUID, session_id: str | None) -> UUID: ...

    async def get_conversation(self, conversation_id: UUID) -> ConversationRecord | None: ...

    async def add_message(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        citations: tuple[Citation, ...] = (),
        truncated: bool = False,
    ) -> Message: ...

    async def list_messages(self, conversation_id: UUID) -> list[Message]: ...

    async def search_chunks(
        self, document_id: UUID, embedding: list[float], limit: int
    ) -> list[RetrievedChunk]: ...


def serialize_citations(citations: tuple[Citation, ...]) -> str:
    """Converte as citações no texto JSON que entra na coluna `jsonb`.

    Vive numa função própria, e não embutida no `INSERT`, porque é aqui que o
    tipo do domínio e o do banco se encontram — o único lugar do módulo onde um
    erro passaria calado, gravando `[]` ou um objeto de chaves erradas sem que
    nada falhe até alguém abrir o histórico. Sendo função, tem teste offline.

    A saída é `str` e entra como parâmetro (`$4::jsonb`), nunca concatenada na
    query: o cast é do Postgres, o valor continua sendo dado.
    """
    return json.dumps(
        [
            {
                "page_number": citation.page_number,
                "snippet": citation.snippet,
                "chunk_index": citation.chunk_index,
                "score": citation.score,
            }
            for citation in citations
        ],
        ensure_ascii=False,
    )


def deserialize_citations(raw: object) -> tuple[Citation, ...]:
    """Reconstrói as citações lidas da coluna `jsonb`.

    O asyncpg **não** decodifica `jsonb` por padrão: o valor volta como `str`
    com o JSON dentro, e não como lista. Tratar isso explicitamente aqui é o que
    evita o bug clássico de iterar a string caractere a caractere e produzir uma
    lista de citações vazia sem nenhuma exceção. Um codec registrado no pool
    resolveria também, mas esconderia a conversão dentro da configuração da
    conexão, longe do teste.

    Um payload que não seja uma lista de objetos com os quatro campos é
    inconsistência de schema, não entrada de usuário: vira `InternalError` em
    vez de citação silenciosamente vazia, que a UI exibiria como resposta sem
    fundamento.
    """
    if raw is None:
        return ()
    if isinstance(raw, bytes | bytearray):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InternalError("As citações gravadas não são um JSON válido.") from exc
    if not isinstance(raw, list):
        raise InternalError("As citações gravadas não são uma lista.")
    try:
        return tuple(
            Citation(
                page_number=int(item["page_number"]),
                snippet=str(item["snippet"]),
                chunk_index=int(item["chunk_index"]),
                score=float(item["score"]),
            )
            for item in raw
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InternalError("As citações gravadas não têm o formato esperado.") from exc


def vector_literal(values: list[float]) -> str:
    """Formata o vetor no literal que o pgvector aceita.

    O valor continua entrando como parâmetro (`$5::vector`); o que esta função
    produz é o conteúdo do parâmetro, nunca um pedaço da query.
    """
    return "[" + ",".join(repr(float(value)) for value in values) + "]"


class PostgresDocumentRepository:
    """Implementação sobre o pool asyncpg criado no lifespan."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self, filename: str, content_hash: str, session_id: str | None) -> UUID:
        """Grava o documento em `pending` e devolve o id gerado pelo banco."""
        document_id = await self._database.pool.fetchval(
            _CREATE_SQL, filename, content_hash, DocumentStatus.PENDING.value, session_id
        )
        return UUID(str(document_id))

    async def get(self, document_id: UUID) -> DocumentRecord | None:
        """Lê o estado de um documento, ou `None` se ele não existir.

        Devolver `None` em vez de levantar mantém a decisão de virar `404` na
        rota, que é quem conhece o envelope de erro.
        """
        row = await self._database.pool.fetchrow(_GET_SQL, document_id)
        return _to_record(row)

    async def find_by_hash(
        self, session_id: str | None, content_hash: str
    ) -> DocumentRecord | None:
        """Procura documento idêntico já enviado na mesma sessão.

        `IS NOT DISTINCT FROM` em vez de `=` porque `session_id` pode ser nulo, e
        `NULL = NULL` seria falso — sem isso, quem não manda o header reprocessa
        o mesmo PDF a cada envio, queimando quota à toa.
        """
        row = await self._database.pool.fetchrow(_FIND_BY_HASH_SQL, session_id, content_hash)
        return _to_record(row)

    async def set_status(
        self, document_id: UUID, status: DocumentStatus, error_message: str | None = None
    ) -> None:
        """Move o documento de estado, gravando junto a mensagem ao usuário.

        `error_message` é escrita sempre, inclusive como `NULL`: assim uma
        transição de saída de `failed` não deixa para trás o texto do erro
        anterior, que a tela exibiria como se ainda valesse.
        """
        await self._database.pool.execute(_SET_STATUS_SQL, document_id, status.value, error_message)

    async def set_totals(self, document_id: UUID, page_count: int, chunks_total: int) -> None:
        """Publica os totais assim que o chunking termina.

        Enquanto `chunks_total` é nulo a tela mostra progresso indeterminado —
        é a ausência deste valor que a distingue de "processou zero chunks".
        """
        await self._database.pool.execute(_SET_TOTALS_SQL, document_id, page_count, chunks_total)

    async def update_progress(self, document_id: UUID, chunks_processed: int) -> None:
        """Grava quantos chunks já foram embedados.

        Chamada a cada lote, e não ao final, porque a ingestão passa de meio
        minuto no teto da spec e uma barra parada em zero parece travamento.
        """
        await self._database.pool.execute(_UPDATE_PROGRESS_SQL, document_id, chunks_processed)

    async def insert_chunks(
        self, document_id: UUID, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        """Grava os chunks numa única viagem, dentro de uma transação.

        Em lote e não um por vez porque são dezenas de linhas por documento, e
        cada ida ao banco custa mais que a inserção em si.
        """
        rows = [
            (
                document_id,
                chunk.chunk_index,
                chunk.page_number,
                chunk.content,
                vector_literal(embedding),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        async with self._database.pool.acquire() as connection, connection.transaction():
            await connection.executemany(_INSERT_CHUNK_SQL, rows)

    async def reset_for_retry(self, document_id: UUID) -> None:
        """Devolve um documento que falhou ao estado inicial, para reprocessar.

        Reaproveita a linha existente em vez de criar outra porque
        `UNIQUE (session_id, content_hash)` impediria a segunda — e porque o
        usuário espera reenviar "o mesmo documento", não ganhar um id novo.

        Os chunks são apagados junto: se a falha aconteceu depois da inserção,
        reprocessar sem limpar duplicaria o conteúdo indexado.
        """
        async with self._database.pool.acquire() as connection, connection.transaction():
            await connection.execute(_DELETE_CHUNKS_SQL, document_id)
            await connection.execute(
                _RESET_FOR_RETRY_SQL, document_id, DocumentStatus.PENDING.value
            )

    async def sweep_orphans(self) -> int:
        """Delega ao `Database`, que já implementa a varredura usada no startup."""
        return await self._database.sweep_orphans()


class PostgresConversationRepository:
    """Implementação de `ConversationRepository` sobre o mesmo pool asyncpg.

    Classe própria, e não métodos novos em `PostgresDocumentRepository`: as duas
    compartilham só o pool, e a rota de chat da fase A.4 recebe exatamente a
    fatia de que precisa. Construí-la custa um atributo, então tê-las separadas
    não cria trabalho de fiação no `Depends`.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_conversation(self, document_id: UUID, session_id: str | None) -> UUID:
        """Abre uma conversa presa ao documento e devolve o id gerado pelo banco.

        Quem valida que o documento está `ready` é a rota (FR-1), não aqui: o
        repositório não conhece o envelope de erro nem o status HTTP que essa
        recusa exige. A FK garante apenas que o documento existe.
        """
        conversation_id = await self._database.pool.fetchval(
            _CREATE_CONVERSATION_SQL, document_id, session_id
        )
        return UUID(str(conversation_id))

    async def get_conversation(self, conversation_id: UUID) -> ConversationRecord | None:
        """Lê a conversa, ou `None` se ela não existir.

        `None` em vez de exceção pelo mesmo motivo de `DocumentRepository.get`:
        traduzir ausência em `404` é decisão da rota, que é quem conhece o
        envelope `{code, message}`. Aqui, "não existe" é resposta, não falha.
        """
        row = await self._database.pool.fetchrow(_GET_CONVERSATION_SQL, conversation_id)
        if row is None:
            return None
        return ConversationRecord(
            id=UUID(str(row["id"])),
            document_id=UUID(str(row["document_id"])),
            session_id=row["session_id"],
            created_at=row["created_at"],
        )

    async def add_message(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        citations: tuple[Citation, ...] = (),
        truncated: bool = False,
    ) -> Message:
        """Grava uma mensagem e devolve a linha como o banco a materializou.

        Devolve a `Message` inteira, e não só o id, porque quem chama precisa dos
        dois valores que o banco gera: o `id` vai no evento SSE `done` e o
        `created_at` entra no histórico sem uma segunda ida ao banco.

        `citations` e `truncated` têm default porque a pergunta do usuário é
        persistida **antes** da chamada ao LLM (FR-9), quando nenhum dos dois
        existe ainda — obrigar `((), False)` em cada chamada só convidaria a
        confundir a ordem dos argumentos.
        """
        row = await self._database.pool.fetchrow(
            _ADD_MESSAGE_SQL,
            conversation_id,
            role.value,
            content,
            serialize_citations(citations),
            truncated,
        )
        if row is None:  # pragma: no cover - INSERT ... RETURNING sempre devolve linha
            raise InternalError("A mensagem não pôde ser gravada.")
        return _to_message(row)

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        """Devolve o histórico da conversa em ordem cronológica.

        Sem paginação de propósito: a janela do prompt é recortada em `core/`
        (NFR-5) e a UI mostra a conversa inteira, que é de uma sessão só. Um
        `LIMIT` aqui truncaria o histórico exibido sem que ninguém pedisse.

        Conversa inexistente e conversa vazia devolvem a mesma lista vazia — a
        distinção, quando importa, é feita por `get_conversation`.
        """
        rows = await self._database.pool.fetch(_LIST_MESSAGES_SQL, conversation_id)
        return [_to_message(row) for row in rows]

    async def search_chunks(
        self, document_id: UUID, embedding: list[float], limit: int
    ) -> list[RetrievedChunk]:
        """Recupera os `limit` chunks mais próximos da pergunta, só deste documento.

        O `document_id` não é parâmetro opcional nem filtro aplicado depois: ele
        entra no `WHERE` da própria busca, para que um chunk de outro PDF não
        chegue sequer a ser candidato. Filtrar em Python o que voltou seria pior
        de duas formas — gastaria vizinhos do top-k com trechos que já se sabe
        que serão descartados, e deixaria o isolamento na mão de quem chama.

        A distância volta convertida em similaridade por `core.retrieval`, e não
        crua, porque `1 - distância` só é um cosseno legítimo com os vetores
        normalizados em L2 — condição que o adapter de embeddings garante e que
        precisa valer nos dois lados da conta. O resto do pipeline recebe um
        score em `[0,1]` e nunca precisa saber que existiu uma distância.

        A transação existe só para o `SET LOCAL` da varredura iterativa (ver a
        constante): é ele que garante que o `LIMIT` pedido seja o `LIMIT`
        entregue quando o planejador escolhe o índice HNSW.
        """
        async with self._database.pool.acquire() as connection, connection.transaction():
            await connection.execute(_ITERATIVE_SCAN_SQL)
            rows = await connection.fetch(
                _SEARCH_CHUNKS_SQL, document_id, vector_literal(embedding), limit
            )
        return [
            RetrievedChunk(
                chunk_index=row["chunk_index"],
                page_number=row["page_number"],
                content=row["content"],
                score=similarity_from_distance(float(row["distance"])),
            )
            for row in rows
        ]


def _to_message(row: Any) -> Message:
    return Message(
        id=int(row["id"]),
        role=MessageRole(row["role"]),
        content=row["content"],
        citations=deserialize_citations(row["citations"]),
        truncated=row["truncated"],
        created_at=row["created_at"],
    )


def _to_record(row: Any) -> DocumentRecord | None:
    if row is None:
        return None
    return DocumentRecord(
        id=UUID(str(row["id"])),
        filename=row["filename"],
        status=DocumentStatus(row["status"]),
        error_message=row["error_message"],
        page_count=row["page_count"],
        chunks_total=row["chunks_total"],
        chunks_processed=row["chunks_processed"],
    )
