---
spec: 01-ingestao-pdf
fase: A.4
slug_fase: ingestion-pipeline
status: rework
tentativa: 2
reprovacoes: 1
sha_inicial: a3a775c
sha_final: 8cc9eb14ab19faed861817a6e74ef2871b901c52
range: a3a775c..8cc9eb14ab19faed861817a6e74ef2871b901c52
---

# FASE A.4 — Relatório de execução

## 1. Resumo do que foi feito

O requisito 1 do escopo passa a existir de fato: `POST /api/documents` aceita o
PDF e responde `202` em milissegundos, e o pipeline de background leva o
documento por `pending → processing → ready`, com progresso consultável. A
divisão do que se valida onde é a decisão central — na requisição ficam só as
checagens baratas, e tudo que exige abrir o PDF acontece no background, onde a
falha vira `failed` com mensagem em pt-BR em vez de segurar um request.
Verificado contra o compose real: o `documento-de-exemplo.pdf` chega a `ready` com 3
páginas e 10 chunks, todos com 768 dimensões e norma L2 igual a 1.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `backend/app/adapters/repository.py` | Protocolo `DocumentRepository`, `DocumentRecord` e a implementação Postgres com SQL parametrizado |
| `backend/app/ingestion.py` | O pipeline: semáforo global, extração fora do event loop, chunking, embeddings em lote com progresso, persistência e a máquina de estados |
| `backend/app/api/documents.py` | `POST /api/documents` e `GET /api/documents/{id}`, mais as dependências que injetam repositório e embedder |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/app/main.py` | Lifespan monta `PostgresDocumentRepository` e `GeminiEmbeddingClient`; a varredura de órfãos passa a ser chamada pelo repositório; router de documentos montado em `/api` |
| `backend/app/api/schemas.py` | `UploadAcceptedResponse` e `DocumentResponse` |
| `backend/app/logging_setup.py` | `bind_document_id()` e filtro em DEBUG — ver desvio 2 |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado, e este era o ponto da fase.** `extract_pages` (A.2) e
`chunk_pages` (A.2) são chamados como estão, sem reimplementação. O
`EmbeddingClient` (A.3) é consumido pelo protocolo, não pela classe concreta.
`Database.sweep_orphans` (A.1) é **delegado** pelo repositório, não duplicado —
era exatamente a regressão que o relatório da A.1 pediu para vigiar. Nenhuma
chamada ao Gemini existe fora do adapter da A.3, e o PDF é parseado **uma vez
só** (`extract_pages` roda uma vez e o resultado é reusado).

**Decisões de design.**

- **`Content-Length` conferido antes de tocar no corpo**, e leitura em pedaços
  com corte rígido depois. O segundo controle existe porque o `Content-Length` é
  informado pelo cliente e pode mentir; sem ele o limite seria sugestão.
  *Consequência medida:* o limite se aplica ao corpo da requisição, então a
  sobrecarga do multipart (~200 bytes) conta. Um arquivo de exatamente 25 MiB é
  recusado. É o que a FR-2 pede literalmente ("rejeita `Content-Length` acima de
  `MAX_UPLOAD_MB`"), e a diferença é irrelevante na prática, mas registro.
- **A rota lê o formulário cru (`request.form()`) em vez de declarar
  `UploadFile` na assinatura.** Se o `UploadFile` estivesse na assinatura, o
  framework consumiria o corpo inteiro antes de o código rodar, e a checagem de
  tamanho chegaria tarde demais para servir de proteção. Verificado na fonte do
  Starlette 1.6: o `max_part_size` padrão de 1 MB só se aplica a campos que
  **não** são arquivo, então PDFs de dezenas de MB passam sem truncar.
- **`asyncio.to_thread` em dois pontos**, não um: no `pypdf` (a A.2 avisou na
  docstring) **e** no `embed_documents`, que é síncrono no SDK do provedor.
  Deixar o segundo no event loop travaria a API durante toda a chamada de rede.
- **A ingestão fatia os chunks em lotes ela mesma** e chama `embed_documents`
  uma vez por lote, em vez de entregar a lista inteira. O total de requisições
  continua sendo `ceil(N/B)`, mas assim o progresso é gravado **entre** lotes —
  que é o que a NFR-1 exige. Entregar tudo de uma vez daria uma barra parada em
  zero por dezenas de segundos.
- **`find_by_hash` usa `IS NOT DISTINCT FROM`** e não `=`, porque `session_id`
  pode ser nulo e `NULL = NULL` é falso. Sem isso, quem não manda o header
  reprocessaria o mesmo PDF a cada envio, queimando quota à toa.
- **`_fail` é o único ponto de saída por erro** do pipeline, e ele mesmo trata a
  falha de gravar a falha (se nem o banco responde, o log registra e a varredura
  do próximo startup resolve). É o que sustenta a garantia de FR-9.
- **O `request_id` é capturado no contexto da requisição** e passado por
  parâmetro para a task, que o reamarra junto do `document_id`. Dentro da task o
  contexto da requisição já não existe — sem isso, o AC-18 não fecharia. Isso
  resolve a pendência nº 2 deixada pelo relatório da A.3.
- **Repositório e embedder entram por dependência do FastAPI**, lidos de
  `app.state`, no mesmo padrão do `get_database` da A.1. É o que permitirá à A.5
  injetar os fakes por `dependency_overrides`.

**Desvios da spec — dois, declarados.**

1. **`set_totals` acrescentado ao protocolo do repositório.** A spec lista
   `create`, `get`, `find_by_hash`, `set_status`, `update_progress`,
   `insert_chunks` e `sweep_orphans`. Faltava por onde gravar `page_count` e
   `chunks_total`, que a FR-10 exige na resposta e a B.4 usa para decidir entre
   barra determinada e indeterminada. Preferi um método explícito a sobrecarregar
   `update_progress` com parâmetros opcionais.
2. **`backend/app/logging_setup.py` alterado** (não estava na lista da fase).
   Duas mudanças: `bind_document_id()`, sem a qual os eventos do pipeline não
   carregariam `document_id` como a §4.4 exige; e o filtro do structlog baixado
   de INFO para DEBUG. **A razão do segundo é um conflito real dentro da spec:**
   a §4.4 cataloga `embedding.batch` como nível `debug`, e o AC-18 exige
   encontrar no log "eventos nomeados para ... cada lote de embedding". Com o
   filtro em INFO os dois não podem valer ao mesmo tempo. Baixei o filtro, que é
   a opção que não mexe no nível catalogado. Era a pendência nº 1 do relatório da
   A.3, e fica registrada aqui para o avaliador confirmar ou mandar inverter.

Nenhuma violação do escopo travado: nenhuma chamada ao Gemini fora do adapter da
A.3, nenhum SQL concatenado (todo parâmetro é `$n`, inclusive o vetor, que entra
como `$5::vector`), nenhum documento fica preso em `processing` (verificado no
banco: só `ready` e `failed`), o PDF não é parseado duas vezes, o event loop não
é bloqueado, nada de retrieval ou chat, e o conteúdo do PDF não vai para log.
**As três exceções de PDF da A.2 continuam sendo levantadas só no background**,
como o relatório dela pediu — o caminho da requisição usa apenas
`arquivo_grande` e `arquivo_invalido`, ambos na tabela §4.3.

## 5. Comandos rodados + saídas reais

```text
# lint / type / arch / testes / segurança
$ uv run ruff check .            -> All checks passed!
$ uv run mypy app                -> Success: no issues found in 18 source files
$ uv run lint-imports            -> Contracts: 3 kept, 0 broken.
$ uv run pytest -q               -> 68 passed in 2.78s
$ uv run bandit -q -r app        -> (sem saída; 0 achados)

# ---- gate de conclusão: upload real através do nginx ----
$ curl -X POST http://localhost:5273/api/documents \
       -H 'X-Session-Id: sessao-teste-a4' -F "file=@documento-de-exemplo.pdf"
HTTP/1.1 202 Accepted
x-request-id: d8591d03-67b0-48e4-8064-665d21177ae1
{"id":"fabf9b43-fccf-4859-8f2a-1bd3c166f130","status":"pending"}

# polling
t=1s {"status":"processing","page_count":null,"chunks_total":null,"chunks_processed":0}
t=2s {"status":"ready","page_count":3,"chunks_total":10,"chunks_processed":10,
      "error_message":null}

# ---- AC-18: a ingestão inteira num único grep por request_id ----
$ docker compose logs backend | grep d8591d03-67b0-48e4-8064-665d21177ae1
{"document_id":"fabf9b43...","filename":"documento-de-exemplo.pdf","size_bytes":259731,
 "event":"document.received","request_id":"d8591d03...","level":"info", ...}
{"page_count":3,"char_count":3665,"duration_ms":307,"event":"document.extracted",
 "request_id":"d8591d03...","document_id":"fabf9b43...","level":"info", ...}
{"chunk_count":10,"duration_ms":0,"event":"document.chunked",
 "request_id":"d8591d03...","document_id":"fabf9b43...","level":"info", ...}
{"batch_index":0,"batch_size":10,"duration_ms":1070,"event":"embedding.batch",
 "request_id":"d8591d03...","document_id":"fabf9b43...","level":"debug", ...}
{"chunk_count":10,"total_duration_ms":1412,"event":"document.ready",
 "request_id":"d8591d03...","document_id":"fabf9b43...","level":"info", ...}

# ---- AC-11: os chunks no banco (chunk_index | page | chars | dims | norma L2) ----
0|1|498|768|1.000000     4|2|456|768|1.000000     8|3|472|768|1.000000
1|1|473|768|1.000000     5|2|427|768|1.000000     9|3|390|768|1.000000
2|1|447|768|1.000000     6|2|465|768|1.000000
3|1|397|768|1.000000     7|2|367|768|1.000000
$ SELECT count(*), count(embedding) FROM chunks;   -> 10 | 10   (nenhum nulo)
$ SELECT indexdef FROM pg_indexes WHERE tablename='chunks';
CREATE INDEX chunks_embedding_idx ON public.chunks USING hnsw (embedding vector_cosine_ops)

# ---- AC-2: limites de upload, medidos através do nginx ----
30.000.000 bytes  -> HTTP 413 {"code":"arquivo_grande","message":"O arquivo excede o limite de 25 MB."}
27.000.000 bytes  -> HTTP 413 {"code":"arquivo_grande", ...}
31.457.280 bytes  -> HTTP 413 HTML do nginx  (client_max_body_size 30m corta antes — ver §9)

# ---- AC-3: .txt renomeado para .pdf ----
HTTP 422 {"code":"arquivo_invalido","message":"O arquivo enviado não é um PDF. ..."}

# ---- AC-15: reenvio idêntico na mesma sessão ----
2o envio -> {"id":"fabf9b43-... (o MESMO)","status":"ready"}
chunks antes=10  depois=10        documentos no banco=1
{"document_id":"fabf9b43...","content_hash":"e2e53e71...","event":"document.duplicate"}

# ---- AC-28: dois uploads disparados ao mesmo tempo ----
17:38:57.026  39eb34e0  document.extracted
17:38:57.026  39eb34e0  document.chunked
17:38:57.783  39eb34e0  document.ready      <- A termina
17:38:57.790  518a1178  document.extracted  <- só então B começa
17:38:57.790  518a1178  document.chunked
17:38:58.463  518a1178  document.ready

# ---- AC-4 / AC-5: falhas de parse, no background ----
25 páginas com MAX_PDF_PAGES=20 -> status failed,
  "O PDF tem 25 páginas e o limite é 20. Envie um documento menor."
PDF sem camada de texto          -> status failed,
  "PDF sem texto extraível; OCR não é suportado. Envie um PDF com camada de
   texto, não um documento escaneado."

# ---- FR-9: nenhum documento preso ----
$ SELECT status, count(*) FROM documents GROUP BY status;
failed|2      ready|3        (nenhum pending, nenhum processing)

# ---- NFR-3 / AC-19: segredo em log? ----
$ docker compose logs backend | grep -c '<a chave>'      -> 0
$ docker compose logs backend | grep -c 'postgresql://'  -> 0

# frontend (lint + tsc) — [—] NÃO RODADO
# Justificativa: frontend/src é entregável do Track B, em execução paralela em
# outra branch. Mesma justificativa das fases A.1 a A.3.
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-1** (`202` com `{id, status:"pending"}`, processamento em background)
  — resposta literal colada acima; o `202` volta antes de qualquer processamento
  e o polling seguinte mostra `processing`.
- [x] **AC-2** (30 MB → `413` JSON pelo nginx, não HTML) — 30.000.000 bytes
  devolvem `{"code":"arquivo_grande"}`. Ressalva medida e honesta em §9.
- [x] **AC-3** (`.txt` renomeado → `422` `arquivo_invalido`) — saída colada.
- [x] **AC-4** (páginas acima do limite → `failed` citando o limite) — PDF de 25
  páginas com `MAX_PDF_PAGES=20`, mensagem colada.
- [x] **AC-5** (sem texto extraível → `failed` explicando que não há OCR) —
  mensagem colada.
- [x] **AC-11** (colunas e índice) — as 10 linhas com `document_id`,
  `page_number`, `chunk_index`, `content` e `embedding` não nulo; índice HNSW
  `vector_cosine_ops` conferido em `pg_indexes`. **A norma L2 de todo vetor
  gravado é 1,000000**, o que prova que a normalização da A.3 sobreviveu à
  persistência.
- [x] **AC-12** (progresso monotônico até `chunks_total`) — observado
  `chunks_processed: 0 → 10` com `chunks_total: 10`. *Ressalva honesta:* com 10
  chunks cabendo num único lote de 16, só houve **uma** atualização de progresso.
  O comportamento monotônico com vários lotes é exercitado offline na A.5.
- [x] **AC-15** (reenvio idêntico não reprocessa) — o segundo envio devolve o
  mesmo `id`, a contagem de chunks não muda, há **um** documento no banco, e o
  evento `document.duplicate` foi emitido. Nenhum embedding novo foi gerado.
- [x] **AC-18** (eventos nomeados com o mesmo `request_id` e `duration_ms`) — os
  cinco eventos colados acima, todos com o mesmo `request_id` **e** o mesmo
  `document_id`, cada um com sua duração.
- [x] **AC-28** (dois uploads simultâneos serializam) — a linha do tempo mostra
  o pipeline de B começando 7 ms **depois** de A concluir.
- [x] **FR-9** (nenhum documento preso em `processing`) — consulta agregada
  colada: só `ready` e `failed`.
- [x] **AC-13 (a parte desta fase)** — nenhuma chave aparece em log; `grep`
  retornou 0. O caminho de falha permanente do provedor é exercitado offline na
  A.3 e será coberto ponta a ponta na A.5.

## 7. Definition of Done da fase

- [x] Testes verdes — 68 passando (as fases A.1–A.3 seguem verdes; os testes
      **desta** fase são entregáveis declarados da A.5, não desta).
- [x] Comandos de validação limpos — ruff, mypy strict, lint-imports, bandit.
      Gates de frontend `[—]` justificados.
- [x] Escopo travado respeitado — nenhuma violação BLOQUEANTE da §5.
- [x] Nenhum segredo/PII em log/DTO/exceção — `grep` da chave e do DSN: 0.
- [x] Commits em pt-BR (Conventional Commits).

## 8. (Em rework) O que mudou nesta tentativa

Tentativa 2, motivada pelo veredito **RESSALVAS** (score 9,3). Dois achados
IMPORTANTES e uma sugestão implementada.

### I-1 · Documento `failed` deduplicado para sempre — CORRIGIDO

A checagem de dedup não olhava o `status`. O sistema exibia "Tente enviar de
novo" e, quando o usuário obedecia, devolvia o mesmo registro falho sem
reprocessar. Como a chave é `(session_id, content_hash)` e o `session_id` vive
no `localStorage`, **a única saída era limpar o navegador** — o sistema
instruía uma ação que ele próprio impedia. Somado ao furo de retry da `A.3`,
qualquer oscilação de rede produzia esse estado.

Correção em `app/api/documents.py`: o dedup passa a exigir que o estado não seja
`FAILED`, e o caminho de falha **reaproveita a linha existente** via
`reset_for_retry` — criar outra colidiria com `UNIQUE (session_id, content_hash)`,
e o usuário espera reenviar "o mesmo documento", não ganhar um id novo. O novo
método do repositório limpa status, mensagem, totais e progresso, e **apaga os
chunks** na mesma transação: se a falha tivesse acontecido depois da inserção,
reprocessar sem limpar duplicaria o conteúdo indexado. Evento `document.retry`
distingue o caso do `document.duplicate` no log.

Verificado ponta a ponta no compose, com o provedor falhando de verdade
(backend subido com chave inválida) e depois funcionando:

```text
1o envio -> failed | O provedor de IA recusou o conteúdo enviado.
2o envio -> mesmo id  (7871c4ea-…)
estado final: ready | page_count 3 | chunks 10/10 | error_message null
{"event": "document.retry", "document_id": "7871c4ea-…", "request_id": "a1a567ba-…"}
```

Dois testes novos: o do reprocessamento e **o da contrapartida** — reenvio de
documento `ready` continua sem reprocessar, que é o AC-15 e o que protege a
quota. **Verificado por mutação:** removendo a condição de status, o teste falha.

### I-2 · Quatro métodos públicos sem docstring — CORRIGIDO

`get`, `set_status`, `set_totals` e `update_progress` de
`PostgresDocumentRepository` não tinham docstring, contra a NFR-9 e o AC-29 —
enquanto os quatro vizinhos tinham. A afirmação "verificado à mão" do relatório
da `A.5` não se sustentou, e a varredura por AST do avaliador provou isso.
Cada um ganhou docstring dizendo o que faz **e por quê**, no padrão do arquivo.
`reset_for_retry`, criado nesta tentativa, também.

### S-1 · Documento sem chunk nenhum não termina `ready` — IMPLEMENTADO, com ressalva honesta

Guarda em `app/ingestion.py`: chunking vazio levanta `PdfWithoutTextError`.

**A ressalva importa mais que o guarda.** Medi que ele é **inalcançável hoje**:
a suíte inteira passa sem ele, porque o `strip()` do adapter e o
`normalize_whitespace` do núcleo concordam sobre o que é vazio (testei inclusive
espaço fino, NBSP e zero-width). É defesa em profundidade contra uma divergência
futura entre as duas noções, não um caminho vivo.

Por isso o teste **não finge um PDF que o dispare** — ele força a condição
substituindo `chunk_pages`, e a docstring diz exatamente isso. A alternativa
seria deixar código sem cobertura real ou inventar um cenário que não existe;
ambas piores. **Verificado por mutação:** sem o guarda, o teste falha.

### Sugestões não implementadas, e por quê

- **`error_page 413` no nginx:** escopo de infraestrutura, e a B.2 já cobre com
  o fallback de resposta não-JSON. Fora do escopo do rework.
- **`_elapsed_ms` em `document.ready` inclui a espera pelo semáforo.** O
  avaliador pediu para escolher um dos dois sentidos e dizer qual. Escolhido:
  **desde que a task começou**, incluindo a espera — é o número que responde
  "quanto o usuário esperou", que é o que a métrica serve para responder. O
  comportamento não mudou; o que faltava era dizê-lo, e a docstring de
  `run_ingestion` passou a declarar isso explicitamente.

## 9. Itens em aberto / dúvidas para o avaliador

1. **Acima de ~30 MiB quem responde é o nginx, com HTML.** O
   `client_max_body_size 30m` deixa a faixa de 25 a 30 MB para o backend recusar
   em JSON (que é o que o AC-2 pede e o que foi medido), mas um arquivo acima de
   30 MiB é cortado antes de chegar à aplicação e volta como página HTML. Não
   mexi no `nginx.conf`, que é infraestrutura verificada da §4.1. **É
   precisamente o cenário que a B.2 tem que cobrir** com o fallback de resposta
   não-JSON que a spec dela já exige. Se o avaliador quiser JSON sempre, a
   mudança é uma diretiva `error_page 413` no nginx — mas isso é escopo de
   infraestrutura, não desta fase.
2. **Esta fase não tem testes próprios**, por desenho da spec: os arquivos de
   teste da ingestão são entregáveis declarados da A.5. Tudo aqui foi provado
   contra o compose real. Se o avaliador considerar isso insuficiente para
   fechar a fase isoladamente, a A.5 é o remédio já planejado.
3. **AC-12 foi observado com um lote só** (10 chunks < lote de 16), então a
   monotonicidade entre lotes não foi exercitada contra o banco real — só a
   transição `0 → 10`. A A.5 cobre isso offline com um fake que registra as
   chamadas de progresso.
4. **O filtro de log foi baixado para DEBUG** (desvio 2). É a resolução de um
   conflito entre §4.4 e AC-18, e merece o veredito explícito do avaliador: a
   alternativa é promover `embedding.batch` a `info` e devolver o filtro a INFO.
5. **`set_totals` fora da lista do protocolo** (desvio 1) — pequeno, mas é
   acréscimo à interface que a A.5 vai precisar implementar no `FakeRepository`.
