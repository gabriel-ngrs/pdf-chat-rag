---
spec: 02-chat-rag
fase: A.1
slug_fase: conversation-schema
tentativa: 1
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: dd621eb988f9069466a7c125f548ee2d298045e7..1d814cfbdc49d5beb624004042bd7d0a8037eaed
---

# FASE A.1 — Avaliação independente

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. O schema foi conferido **contra o banco em
execução**, não contra o relatório: as duas tabelas, os dois cascades, os dois
índices e os oito tipos de coluna batem literalmente com §4.5 da spec.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | `db/002_conversations.sql:9-33` reproduz §4.5 sem `ALTER TABLE`; nenhuma rota criada no range; inspeção do Postgres real (§6) confirma FKs, índices e defaults |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `backend/app/core/models.py:52-131` só usa `dataclass`/`StrEnum`/`datetime`; `lint-imports` → `Nucleo puro ... KEPT`, `Contracts: 4 kept, 0 broken` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | SQL 100% parametrizado (`repository.py:80-113`); `citations` entra por `$4::jsonb` (`repository.py:95`), o cast é do Postgres e o valor continua dado; grep de segredo no diff = 0 |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `core/models.py` estendido, não duplicado; `ConversationRepository` espelha a forma de `DocumentRepository` (constantes de SQL no topo, `None` para ausência); `db/002` segue `db/001` |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `MessageRole` como `StrEnum` (`models.py:52`); `Message.citations` como `tuple` para `frozen=True` não ser decorativo (`models.py:110-131`) |
| 6 | Local e nomes dos arquivos | 2 | 5 | Os quatro caminhos batem com a lista da fase; nomes em inglês, textos em pt-BR |
| 7 | Qualidade de código | 2 | 5 | `ruff` e `mypy --strict` limpos; docstrings de "por quê" em toda função pública; `deserialize_citations` isolada e testada, que é onde o erro silencioso nasceria |
| 8 | Testes e cobertura | 2 | 5 | 15 offline + 7 sob `db`, incluindo cinco payloads corrompidos e as três formas em que o `jsonb` chega; re-executados por mim (§6) |
| 9 | Migration safety (se aplicável) | 2 | 4 | Cascades e índices verificados no banco vivo; desconta: `make down && make up` completo não foi executado (o equivalente `down -v` + `up -d db` foi), e `role` é `text` sem `CHECK` |

Score = (5·3 + 5·3 + 5·3 + 5·3 + 5·2 + 5·2 + 5·2 + 5·2 + 4·2) / 22 × 2 = **9.8**

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **`db/002_conversations.sql:22` — `role text NOT NULL` sem `CHECK`.** A spec
  escreve a coluna assim em §4.5, então isto não é desvio. Mas `_to_message`
  (`repository.py:517`) faz `MessageRole(row["role"])`: uma linha com papel
  inválido só estoura na **leitura** do histórico, longe de quem a gravou. Um
  `CHECK (role IN ('user','assistant'))` moveria a falha para o `INSERT`. Se
  entrar, exige `make down` — vale avaliar se compensa a esta altura.
- **`repository.py:411` — `get_conversation` não filtra por `session_id`.** Quem
  tiver o uuid da conversa lê o histórico dela. É coerente com a `FEAT-0001` (o
  `session_id` organiza, não protege) e a fase não pede isolamento — mas é item
  para "limitações conhecidas" do README na `B.5`, junto com o que já está
  previsto lá.
- **`repository.py:104` — `ORDER BY created_at, id`.** O desempate por `id` é
  acerto de projeto e está justificado em comentário; não há teste que force a
  colisão (o próprio relatório reconhece que o teste seria frágil). Concordo com
  a decisão; fica registrado que a garantia é de desenho, não de suíte.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh \
       .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ ids de fase únicos (12 fases)
✓ heading de cada fase casa com o bullet `id`
✓ todos os slugs são kebab-case
✓ wave: multi com ao menos um id `<TRACK>.<n>`
✓ todo `id` em "Depende de" existe na §5
✓ cada track tem 3–8 fases
✓ grafo de dependências acíclico
✓ §5 estruturalmente válida
EXIT=0

$ git merge-base --is-ancestor 1d814cf HEAD && echo OK
OK

$ make check
Contracts: 4 kept, 0 broken.
...
app/core/models.py            40      0      0      0   100%
Required test coverage of 90% reached. Total coverage: 99.55%
248 passed, 17 deselected in 11.67s
Test Files  10 passed (10) | Tests  75 passed (75)
[exited with code 0]

$ make security
cd backend && uv run bandit -q -r app
cd backend && uv run pip-audit
No known vulnerabilities found
cd frontend && npm audit --audit-level=high
found 0 vulnerabilities
SEC_EXIT=0

$ cd backend && uv run pytest -m db -p no:cacheprovider --no-cov -q
17 passed, 248 deselected in 3.42s
```

Inspeção do **Postgres em execução** (o schema real, não o arquivo):

```text
FK: conversations_document_id_fkey  FOREIGN KEY (document_id)
      REFERENCES documents(id) ON DELETE CASCADE
FK: messages_conversation_id_fkey   FOREIGN KEY (conversation_id)
      REFERENCES conversations(id) ON DELETE CASCADE

IDX: conversations_document_id_idx            btree (document_id)
IDX: messages_conversation_id_created_at_idx  btree (conversation_id, created_at)

COL: conversations.id          uuid        NOT NULL  default gen_random_uuid()
COL: conversations.document_id uuid        NOT NULL
COL: conversations.session_id  text        NULL
COL: conversations.created_at  timestamptz NOT NULL  default now()
COL: messages.id               bigint      NOT NULL  default nextval('messages_id_seq')
COL: messages.conversation_id  uuid        NOT NULL
COL: messages.role             text        NOT NULL
COL: messages.content          text        NOT NULL
COL: messages.citations        jsonb       NOT NULL  default '[]'::jsonb
COL: messages.truncated        boolean     NOT NULL  default false
COL: messages.created_at       timestamptz NOT NULL  default now()
```

Grep de segredo/PII no diff da fase:

```text
$ git diff dd621eb..1d814cf | grep -inE "AIza[0-9A-Za-z_-]{10,}|postgresql://[^:]+:[^@]+@"
(nenhuma linha)
```

## 7. Itens da fase / DoD não atendidos

- **`make down && make up` completo** (critério de conclusão da fase) não foi
  executado pelo executor nem por mim — o meu `docker compose` não sobe aqui por
  falta de `.env`. O que foi provado: os dois scripts aplicam em ordem em banco
  vazio (evidência do executor) e o schema resultante está **exatamente** como
  §4.5 pede, o que eu confirmei contra o banco vivo. Considero o gate atendido em
  substância.
- Todos os demais itens da fase (`Passos` 1–5, `Testes`, escopo travado)
  atendidos com evidência.

## 8. Divergências entre o relatório e o código real

Nenhuma. Cada afirmação verificável do `FASE-A.1-...-EXECUCAO.md` foi conferida:
tabelas, cascades, índices, tipos, ausência de `ALTER TABLE`, ausência de rota,
serialização por função dedicada e o desvio declarado do `ORDER BY`. O relatório
descreve o que o código faz.
