---
spec: 01-ingestao-pdf
fase: A.4
slug_fase: ingestion-pipeline
tentativa: 1
veredito: RESSALVAS
score: 9.3
threshold: 8.5
range_avaliado: a3a775c..27093c4b6bc4faccbea96e6962da11c253bf8ab4
---

# FASE A.4 — Avaliação independente

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 9.3 / threshold 8.5

Zero BLOQUEANTES. Dois achados IMPORTANTES: um documento que terminou em
`failed` fica **deduplicado para sempre** — reenviar o mesmo PDF na mesma sessão
devolve o documento falho e nunca reprocessa, enquanto a mensagem exibida ao
usuário diz "Tente enviar de novo"; e o AC-29 (docstring em toda função pública
de `adapters/`) não está cumprido em `repository.py`, ao contrário do que os
relatórios afirmam.

A espinha da fase está certa e foi verificada: `Content-Length` antes do corpo,
corte duro na leitura, `to_thread` nos **dois** pontos bloqueantes, `_fail` como
saída única, progresso por lote, SQL parametrizado, e o `request_id` capturado na
requisição e reamarrado dentro da task.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 4 | AC-1/2/3/4/5/11/12/15/18/28 provados (suíte + banco real); AC-29 falha nas docstrings (§4, I-2); dedup de `failed` cumpre a letra da FR-12 e contraria a intenção (I-1) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `main → api → ingestion → adapters → core` KEPT com `exhaustive`; `DocumentRepository` como `Protocol` (`app/adapters/repository.py:78`) é o que torna a A.5 offline |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | Todo SQL parametrizado, inclusive o vetor (`$5::vector`, `:59-62`); provado contra Postgres real com payload destrutivo (teste da A.6); `filename` armazenado como nome, nunca como caminho |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `extract_pages`/`chunk_pages` consumidos como estão; `sweep_orphans` **delegado** ao `Database` (`:174-176`) — exatamente a regressão que a A.1 pediu para vigiar |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Máquina de estados com `_fail` único (`app/ingestion.py:143-157`); `IS NOT DISTINCT FROM` para `session_id` nulo (`:31-37` do repository) |
| 6 | Local e nomes dos arquivos | 2 | 5 | Os três arquivos novos e os três alterados batem com a §5; a alteração extra em `logging_setup.py` está declarada |
| 7 | Qualidade de código | 2 | 4 | Código limpo e bem justificado; **mas** `get`, `set_status`, `set_totals` e `update_progress` (`repository.py:126,142,147,150`) não têm docstring, contra a NFR-9 |
| 8 | Testes e cobertura | 2 | 4 | A fase não traz testes próprios — é desenho da spec (são entregáveis da A.5) e a A.5 de fato os entregou; a evidência da fase é medição manual contra o compose |
| 9 | Migration safety | 2 | [—] | Não se aplica: a fase não altera schema |

Média ponderada: 93/100 → **9.3**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

### I-1 · Documento `failed` é deduplicado para sempre — `backend/app/api/documents.py:132-135`

```python
existing = await repository.find_by_hash(session_id, content_hash)
if existing is not None:
    logger.info("document.duplicate", ...)
    return UploadAcceptedResponse(id=existing.id, status=existing.status)
```

A checagem não olha o `status`. Reproduzido por mim, ponta a ponta pela rota
real, com o provedor falhando no primeiro envio e funcionando no segundo:

```text
1o envio: 202 {'id': 'dbfc5c75-...', 'status': 'pending'}
estado apos falha: failed | Não foi possível processar o documento por uma falha
                            interna. Tente enviar de novo.
2o envio: 202 {'id': 'dbfc5c75-...', 'status': 'failed'}     <- mesmo id
estado final: failed | (mesma mensagem)
lotes embedados no 2o envio: [...]  (nenhum novo)
```

O sistema instrui o usuário a fazer algo que ele mesmo impede. Como a chave é
`(session_id, content_hash)` e o `session_id` vive no `localStorage`, a única
saída do usuário é limpar o navegador. E o cenário não é hipotético: com o furo
de retry da A.3 (I-1 daquela avaliação), qualquer oscilação de rede produz
exatamente este estado.

A FR-12 lida literalmente ("devolve o documento existente em vez de
reprocessar") autoriza o comportamento, e por isso o achado é IMPORTANTE e não
BLOQUEANTE. Mas o eixo que a spec nomeia como avaliado nesta fase é "tratamento
do upload e de erros", e um erro sem caminho de saída é o defeito clássico desse
eixo.

**Correção sugerida (uma condição):**

```python
if existing is not None and existing.status is not DocumentStatus.FAILED:
    ...
# e, no caminho FAILED, reaproveitar a linha: set_status(pending) + reagendar a task
```

Reaproveitar o registro evita colidir com o `UNIQUE (session_id, content_hash)`.
Um teste em `tests/test_ingestion_api.py` fecha a regressão.

### I-2 · AC-29 não cumprido: métodos públicos de `adapters/` sem docstring — `backend/app/adapters/repository.py:126,142,147,150`

A NFR-9 e o AC-29 exigem docstring em **toda** função pública de `core/` e
`adapters/`. Varredura por AST feita por mim (§6): `PostgresDocumentRepository`
tem `get`, `set_status`, `set_totals` e `update_progress` sem docstring nenhuma —
enquanto `create`, `find_by_hash`, `insert_chunks` e `sweep_orphans`, ao lado,
têm. Os stubs do `Protocol` e os `__init__` também aparecem na varredura; esses
são defensáveis (a classe documenta o conjunto e o corpo é `...`), os quatro
métodos concretos não.

**Correção sugerida:** uma linha em cada, dizendo o que faz e por quê — no padrão
que o resto do arquivo já usa. Se quiser transformar o AC em gate (a A.5 sugere
isso e ficou de fora com razão), a regra `D` do ruff restrita a
`app/core` e `app/adapters` resolve.

## 5. Sugestões

- **S-1 · Documento sem chunk nenhum chega a `ready`.** Verificado: um PDF cuja
  camada de texto é só espaço em branco produz `chunks_total: 0` e status
  `ready` (ver I-1 da avaliação da A.2). Além de corrigir a validação na A.2,
  vale o guarda simétrico aqui: em `app/ingestion.py:106`, se `len(chunks) == 0`,
  terminar `failed` com a mensagem de OCR. Defesa em profundidade barata.
- A faixa acima de ~30 MiB responder HTML do nginx (item 1 da §9) está
  corretamente declarada e é escopo de infraestrutura. `error_page 413 /413.json`
  no `nginx.conf` resolveria; a B.2 já cobre o caso com o fallback de resposta
  não-JSON, então não é urgente.
- `set_totals` (desvio 1) é acréscimo bem julgado: sobrecarregar `update_progress`
  com parâmetros opcionais teria sido pior.
- O filtro de log baixado para DEBUG (desvio 2) é a resolução certa do conflito
  entre §4.4 e AC-18 — ver a seção de decisões na avaliação da A.6 e o resumo
  final. Mantenha o nível catalogado.
- `_elapsed_ms(started)` em `document.ready` inclui o tempo de espera pelo
  semáforo. Com uma ingestão por vez isso é raro, mas o número publicado deixa de
  ser "quanto demorou processar" e passa a ser "quanto demorou desde que
  chegou". Vale escolher um dos dois e dizer qual na docstring.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 27093c4b... HEAD   -> OK
$ cd backend && uv run ruff check .               -> All checks passed!
$ uv run mypy app                                 -> Success: no issues found in 18 source files
$ uv run lint-imports --config .importlinter      -> Contracts: 4 kept, 0 broken.
$ env -u GEMINI_API_KEY DATABASE_URL=<inalcançável> uv run pytest -q
119 passed, 6 deselected in 6.99s

# testes de banco, contra um Postgres descartável que subi de db/001_init.sql
$ uv run pytest -m db -q
6 passed, 119 deselected in 0.77s
```

**Schema real (conferido por mim, container removido ao fim):**

```text
 embedding   | vector(768) | not null
Indexes:  "chunks_embedding_idx" hnsw (embedding vector_cosine_ops)
Foreign-key: chunks_document_id_fkey ... ON DELETE CASCADE
```

**Sonda do reenvio após falha (escrita por mim):** saída colada em §4, I-1.

**Varredura de docstrings (AST, escrita por mim):**

```text
sem docstring: app/adapters/repository.py:126 get
               app/adapters/repository.py:142 set_status
               app/adapters/repository.py:147 set_totals
               app/adapters/repository.py:150 update_progress
               (+ stubs de Protocol e __init__, defensáveis)
```

**Verificação por mutação do semáforo (AC-28, escrita por mim, sem tocar no
repositório):**

```text
sem mutação:  2 passed
com asyncio.Semaphore neutralizado:
  FAILED tests/test_ingestion_api.py::test_dois_pipelines_concorrentes_nao_se_intercalam
  AssertionError: assert [A, B, A, B, A, B, ...] in ([A, B], [B, A])
```

O semáforo global é real e o teste que o guarda não é vácuo.

**Gate de conclusão da fase — `[—]` NÃO REEXECUTADO por mim.** O upload real do
`Exemplo-YAITEC.pdf` pelo compose exige `GEMINI_API_KEY` e `.env`, que o
avaliador não deve manipular. O que verifiquei em substituição: o schema real, os
6 testes de banco, a suíte offline inteira, e as propriedades de chunking contra
o PDF de verdade (3 páginas → 10 chunks), que é o número que o relatório reporta
ter obtido no compose.

## 7. Itens da fase / DoD não atendidos

- **AC-29 (metade das docstrings)** — I-2.
- **Reenvio após falha** — I-1: a FR-12 é cumprida ao pé da letra, a intenção
  não.
- Um documento pode terminar `ready` com zero chunks (S-1).
- O resto do gate de conclusão está atendido pela evidência do executor, coerente
  com tudo que medi.

## 8. Divergências entre o relatório e o código real

1. **"nenhum documento fica preso em `processing`"** — confere: `_fail` é a saída
   única e o `finally` do pipeline garante a transição; reproduzido pela suíte.
2. **A.5 §9 afirma que a metade "docstrings" do AC-29 "foi verificado à mão e
   está satisfeito"** — não está: quatro métodos públicos concretos de
   `repository.py`, criados nesta fase, não têm docstring (I-2).
3. **"o PDF não é parseado duas vezes"** — confere (`app/ingestion.py:88`, uma
   chamada, resultado reusado).
4. **"`asyncio.to_thread` em dois pontos"** — confere (`:88` e `:132`), e é uma
   correção legítima sobre o que a A.2 só podia avisar em docstring.
5. O desvio de `logging_setup.py` está declarado no relatório e é coerente com o
   código (`bind_document_id` + filtro em DEBUG).
