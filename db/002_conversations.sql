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

-- ─── Busca lexical, para a fusão híbrida ─────────────────────────────────────
--
-- A busca densa **borra termo exato**: um e-mail, um telefone ou um nome
-- próprio ficam a milésimos de distância de qualquer outro trecho do mesmo
-- assunto — foi medido no eval da fase A.5, onde a página do e-mail de contato
-- ganhou a primeira posição por 0,001. Quem procura "contato@yaitec.com" não
-- quer o trecho semanticamente parecido; quer aquele token.
--
-- A coluna é `GENERATED ALWAYS AS ... STORED` e não um gatilho: o Postgres
-- mantém o vetor em dia sozinho, e não existe caminho de escrita que possa
-- esquecer de atualizá-lo. Fica em `chunks`, criada em `001`, por `ALTER TABLE`
-- — que aqui é seguro porque este arquivo roda uma vez só, em banco vazio,
-- logo depois de `001`, e a coluna nasce junto com a tabela na prática.
--
-- A config `portuguese` vem de fábrica na imagem `pgvector/pgvector:pg16`: ela
-- aplica stemming e remove stopwords do português, o que é o que faz
-- "serviços" casar com "serviço" sem casar com "e" ou "de".
ALTER TABLE chunks
    ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('portuguese', content)) STORED;

-- GIN e não GiST: o índice é lido muito mais do que escrito (uma ingestão por
-- documento, uma busca por pergunta), que é exatamente o regime em que o GIN
-- ganha.
CREATE INDEX ON chunks USING gin (tsv);
