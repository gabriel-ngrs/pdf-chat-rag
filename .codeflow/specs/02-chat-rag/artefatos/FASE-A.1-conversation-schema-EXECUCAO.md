---
spec: 02-chat-rag
fase: A.1
slug_fase: conversation-schema
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: dd621eb988f9069466a7c125f548ee2d298045e7
sha_final: 1d814cfbdc49d5beb624004042bd7d0a8037eaed
range: dd621eb..1d814cf
---

# FASE A.1 — Relatório de execução

## 1. Resumo do que foi feito

Schema de conversas e mensagens (`db/002_conversations.sql`) com as tabelas de §4.5
literalmente, FKs `ON DELETE CASCADE` declaradas no `CREATE TABLE` e os dois índices
pedidos. `core/models.py` ganhou `MessageRole`, `Citation`, `RetrievedChunk` e `Message`
como dataclasses puras. `adapters/repository.py` ganhou o protocolo
`ConversationRepository`, a implementação Postgres com SQL parametrizado e a
serialização de citações em função dedicada e testada.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `db/002_conversations.sql` | Tabelas `conversations` e `messages`, cascades e índices |
| `backend/tests/test_conversation_repository.py` | 8 testes offline de serialização + 7 sob o marker `db` |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/app/core/models.py` | +`MessageRole`, `Citation`, `RetrievedChunk`, `Message` (puros) |
| `backend/app/adapters/repository.py` | +`ConversationRecord`, protocolo `ConversationRepository`, `serialize_citations`/`deserialize_citations`, `PostgresConversationRepository` |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `core/models.py` foi estendido, não duplicado; `repository.py`
seguiu a forma do `DocumentRepository` existente (constantes de SQL no topo, `None` em
vez de exceção para ausência, docstrings de "por quê"); `db/002` seguiu o padrão de
`db/001`. Nada do que a `FEAT-0001` criou foi reescrito.

**Decisões:**

- **`PostgresConversationRepository` como classe própria**, e não métodos novos em
  `PostgresDocumentRepository`. `tests/fakes.py::FakeRepository` implementa
  estruturalmente `DocumentRepository`; engordar aquele protocolo obrigaria toda a
  suíte de ingestão a arrastar métodos de conversa. A rota da `A.4` injeta só a fatia
  de que precisa.
- **`add_message` devolve a `Message` completa.** A `A.4` precisa do `id` (`int`,
  coerente com `bigserial`) para o evento `done` e do `created_at` para o histórico; o
  `INSERT ... RETURNING` traz os dois numa viagem.
- **`Message.citations` é `tuple`.** Com `list`, `frozen=True` seria decorativo.
- **Citação corrompida levanta `InternalError`** em vez de devolver `()`: tupla vazia
  faria a UI exibir uma resposta fundamentada como se não tivesse fundamento.
- **Desvio menor:** `list_messages` ordena por `created_at, id`, não só `created_at`.
  `created_at` é o instante da transação; duas mensagens no mesmo instante sairiam em
  ordem arbitrária, trocando pergunta e resposta. Justificado em comentário no SQL.

## 5. Comandos rodados + saídas reais

```text
# lint
$ cd backend && uv run ruff check .
All checks passed!

# type-check
$ uv run mypy app
Success: no issues found in 20 source files

# arquitetura
$ uv run lint-imports --config .importlinter
Camadas: main -> api -> ingestion -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Sem ORM nem query builder KEPT
Contracts: 4 kept, 0 broken.

# testes da fase (offline)
$ uv run pytest tests/test_conversation_repository.py -p no:cacheprovider --no-cov -q
...............
15 passed, 7 deselected in 0.04s

# schema aplicado em banco vazio (volume recriado)
$ docker compose down -v && docker compose up -d db
$ docker compose logs db | grep -iE "001_init|002_conversations|error|fatal"
db-1 | ...docker-entrypoint.sh: running /docker-entrypoint-initdb.d/001_init.sql
db-1 | ...docker-entrypoint.sh: running /docker-entrypoint-initdb.d/002_conversations.sql
(nenhuma linha de error/fatal)

# testes contra o Postgres real
$ uv run pytest tests/test_conversation_repository.py -m db -p no:cacheprovider --no-cov -q
.......
7 passed, 15 deselected in 0.40s

# gate agregado do projeto (com A.2 já no working tree)
$ make check
Contracts: 4 kept, 0 broken.
Required test coverage of 90% reached. Total coverage: 99.55%
188 passed, 13 deselected in 10.11s
Test Files  6 passed (6) | Tests  40 passed (40)

# grep de segredo/PII no diff (esperado: 0)
$ git diff dd621eb..1d814cf | grep -ciE "AIza|api[_-]?key *=|postgresql://.*:.*@"
0
```

Schema efetivamente criado, conferido com `\d`:

```text
conversations: id uuid PK default gen_random_uuid() | document_id uuid not null
               | session_id text | created_at timestamptz not null default now()
  índice btree (document_id); FK document_id -> documents(id) ON DELETE CASCADE
messages: id bigint PK nextval | conversation_id uuid not null | role text not null
          | content text not null | citations jsonb not null '[]'::jsonb
          | truncated boolean not null false | created_at timestamptz not null now()
  índice btree (conversation_id, created_at); FK -> conversations(id) ON DELETE CASCADE
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-11 (round-trip com ordem e citações)** — `test_o_historico_atravessa_o_banco_na_ordem_e_com_as_citacoes`: três trocas produzem seis mensagens na ordem, com papéis alternados e citações presas só às respostas.
- [x] **`truncated` persiste** — `test_resposta_parcial_e_gravada_como_truncada`.
- [x] **Conversa inexistente devolve `None`** — `test_conversa_inexistente_devolve_none`.
- [x] **Cascade** — `test_apagar_o_documento_leva_conversa_e_mensagens_junto`.
- [x] **Serialização testada** — 8 testes offline cobrindo identidade, acentuação, as três formas em que o `jsonb` chega (`str`, `bytes`, lista) e cinco payloads corrompidos.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (15 offline + 7 `db`)
- [x] Comandos de validação limpos (`ruff`, `mypy`, `lint-imports`, `pytest`, `make check`)
- [x] Escopo travado respeitado: sem ORM, sem SQL concatenado, sem `ALTER TABLE` para constraint, `core/models.py` puro (contrato `pure-core` KEPT), nenhuma rota implementada
- [x] Nenhum segredo/PII em log, DTO ou exceção
- [x] Commit em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

- **`make down && make up` completo não foi executado**, porque subiria backend e
  frontend no meio de outra fase. O equivalente foi feito e está colado acima:
  `docker compose down -v && docker compose up -d db`, com os dois scripts aplicando em
  ordem e sem erro, e a suíte `db` verde contra esse banco.
- **Colisão de `created_at`** — o desempate por `id` é defesa de projeto; forçar duas
  mensagens no mesmo instante exigiria uma transação artificial e o teste seria mais
  frágil que a garantia.
- **`get_conversation` não filtra por `session_id`.** A spec não pede na `A.1` e a
  `FEAT-0001` também não isola documentos por sessão na leitura. Fica anotado como
  ponto de atenção — quem tiver o `conversation_id` (um uuid) lê a conversa.
- **Execução paralela:** esta fase foi desenvolvida ao mesmo tempo que a `A.2`, em
  arquivos disjuntos, no mesmo worktree. O `range` acima contém só os arquivos desta
  fase; o `make check` colado rodou com as duas no working tree.
