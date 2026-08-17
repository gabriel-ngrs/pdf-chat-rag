-- Schema do TalkDoc. Roda uma única vez, via docker-entrypoint-initdb.d, em
-- banco vazio: alterar este arquivo exige `make down` (que remove o volume)
-- antes do próximo `up`, senão a mudança é silenciosamente ignorada.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE documents (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    filename         text NOT NULL,
    content_hash     text NOT NULL,
    status           text NOT NULL,
    error_message    text,
    page_count       int,
    chunks_total     int,
    chunks_processed int NOT NULL DEFAULT 0,
    session_id       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, content_hash)
);

CREATE TABLE chunks (
    id          bigserial PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index int NOT NULL,
    page_number int NOT NULL,
    content     text NOT NULL,
    embedding   vector(768) NOT NULL
);

-- O opclass é explícito por dois motivos: sem ele o comando falha com
-- "no default operator class", e um índice L2 não seria usado pelo operador
-- de cosseno (<=>) do retrieval.
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
