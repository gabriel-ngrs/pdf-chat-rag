-- Conversas e mensagens do chat. Roda logo depois de `001_init.sql` — o
-- docker-entrypoint-initdb.d executa os arquivos em ordem alfabética —, e vale
-- para ele a mesma regra: só roda em banco vazio, então alterar este arquivo
-- exige `make down` (que remove o volume) antes do próximo `up`.

-- As FKs vão declaradas completas no CREATE TABLE, e não por ALTER TABLE: o
-- Postgres não tem `ADD CONSTRAINT IF NOT EXISTS`, e o entrypoint aborta no
-- primeiro erro, o que deixaria o banco inteiro sem inicializar.
CREATE TABLE conversations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    session_id  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- `citations` é jsonb e não tabela normalizada porque uma citação é fato
-- daquela resposta, não entidade com vida própria: ninguém busca citação por
-- si, atualiza uma isolada ou a compartilha entre mensagens. Normalizar traria
-- um JOIN a cada leitura de histórico sem nenhuma consulta que o justifique.
CREATE TABLE messages (
    id              bigserial PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            text NOT NULL,
    content         text NOT NULL,
    citations       jsonb NOT NULL DEFAULT '[]',
    truncated       bool NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- O Postgres não indexa a coluna que referencia sozinho. Sem este índice, cada
-- exclusão de documento varre `conversations` inteira para achar o que o
-- cascade precisa levar junto.
CREATE INDEX ON conversations (document_id);

-- O histórico é sempre lido por conversa e em ordem cronológica; o índice
-- composto resolve filtro e ordenação de uma vez só.
CREATE INDEX ON messages (conversation_id, created_at);
