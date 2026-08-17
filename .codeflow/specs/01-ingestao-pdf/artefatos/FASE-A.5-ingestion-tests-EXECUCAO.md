---
spec: 01-ingestao-pdf
fase: A.5
slug_fase: ingestion-tests
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: 3901f69
sha_final: 4a3428f
range: 3901f69..4a3428f
---

# FASE A.5 — Relatório de execução

## 1. Resumo do que foi feito

A suíte de ingestão passa a provar o backend de forma determinística e offline:
38 testes sobre dublês em memória, mais 6 marcados `db` contra o Postgres do
compose. A cobertura de `app/core` é medida em **98,98%** e travada por
`--cov-fail-under=90` no `addopts`, o que transforma a NFR-10 em gate. `make
test` roda sem `GEMINI_API_KEY`, sem rede e com `DATABASE_URL` apontando para um
endereço inalcançável — provado empiricamente, não afirmado. Nenhum arquivo de
produção foi tocado por esta fase.

> **Nota de execução paralela.** Rodou em paralelo com a `A.6` (ambas dependem
> só da `A.4`), no mesmo worktree, com propriedade exclusiva de arquivos: esta
> fase foi dona de `pyproject.toml`/`uv.lock`, a `A.6` de `.importlinter`. Por
> isso os dois `sha_inicial` são iguais.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `backend/tests/fakes.py` | `FakeRepository` (dicionário em memória, que **registra as chamadas de `update_progress`**), `FakeEmbeddingClient` (vetor determinístico já normalizado) e os dublês do SDK |
| `backend/tests/conftest.py` | Injeção dos dublês por `dependency_overrides`, captura do structlog em duas fixtures, e o isolamento do semáforo global |
| `backend/tests/test_ingestion_api.py` | 23 testes: rota, máquina de estados, progresso, dedup e concorrência |
| `backend/tests/test_logging.py` | 15 testes: eventos de §4.4, AC-18 e AC-19 |
| `backend/tests/test_ingestion_db.py` | 5 testes sob o marker `db`: AC-11 contra o Postgres real |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/pyproject.toml` | `pytest-cov>=6.0` no grupo dev; `addopts` com `-m 'not db' --cov=app.core --cov-fail-under=90`; marker `db`; `[tool.coverage.*]` com `branch = true` |
| `backend/uv.lock` | Consequência esperada: `pytest-cov 7.1.0` + `coverage 7.15.4` |
| `.gitignore` | `.coverage` e `htmlcov/`, artefatos do pytest-cov |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `tests/factories.py` (A.2) é usada como está para gerar os
PDFs — nenhum gerador novo foi escrito. Os dublês implementam os protocolos
`DocumentRepository` (A.4) e `EmbeddingClient` (A.3) **sem herança**, que era
exatamente o motivo de eles serem `Protocol` e não classe base. O padrão de
teste de rota (`httpx.ASGITransport` + `dependency_overrides`) veio da A.1.

**Decisões de design.**

- **Duas fixtures de captura de log, não uma.** `capture_logs` entrega o *event
  dict* antes da renderização, o que torna as asserções de AC-18 legíveis
  (campos, não string de JSON). Mas ele é **cego a traceback**: entrega o dict
  antes do `format_exc_info`, então `exc_info` fica booleano e o traceback nunca
  aparece. Como traceback é exatamente onde uma credencial vaza sem ninguém ver,
  AC-19 verificado só por `capture_logs` seria garantia falsa. Daí a segunda
  fixture, que roda a cadeia real da aplicação e troca apenas o *sink*.
- **`configure_logging()` antes de `capture_logs`**, porque `capture_logs`
  preserva o `wrapper_class` vigente e é ele que decide o nível mínimo — sem
  isso `embedding.batch` (debug) seria descartado antes de ser capturado. E
  `merge_contextvars` precisa ser reinjetado, porque `capture_logs` limpa a
  cadeia e sem ele `request_id`/`document_id` sumiriam do dict.
- **Adapter real no teste de log, dublê no teste de fluxo.** `embedding.batch`
  nasce dentro do `GeminiEmbeddingClient`; trocar o adapter inteiro por um fake
  apagaria o evento que o AC-18 exige. Então `test_logging.py` usa o adapter
  real com o **transporte** substituído. O que é falso é a rede, não a camada
  sob verificação.
- **`FakeRepository` cede o loop antes de cada operação.** Sem ponto de troca de
  contexto, duas ingestões concorrentes rodariam em sequência por acidente e o
  teste de AC-28 passaria **mesmo com o semáforo removido**. Verificado por
  mutação (§5).
- **`_env_file=None` em todo `Settings` de teste**, para que um `.env` presente
  na máquina de quem roda a suíte não mude os limites e o resultado.

**Desvios da spec — três, declarados.**

1. **Fixture `autouse` que troca `ingestion._pipeline_lock` a cada teste.** O
   semáforo nasce no import e se prende ao primeiro event loop **em que houver
   disputa**; como cada teste roda num loop próprio, o segundo teste que
   disputasse morreria com *"bound to a different event loop"* — falha de
   infraestrutura dependente da ordem de execução. É isolamento de teste, não
   modificação de produção: semáforo global de módulo continua sendo o desenho
   correto para um processo único.
2. **Hook `pytest_configure` que suspende o piso de cobertura sob `-m db`.** O
   `addopts` vale para toda invocação, e `make test-db` roda só os testes de
   banco, que não exercitam `core/` — o piso de 90% derrubava o comando, que é
   gate de conclusão da fase. Como o `Makefile` está fora do escopo desta fase,
   resolvi no `conftest.py`. **O piso continua integralmente válido em `make
   test`**, verificado em §5. *Alternativa mais direta, se o avaliador
   preferir:* `--no-cov` no alvo `test-db` do `Makefile`, e o hook sai inteiro.
3. **`--cov=app.core` (nome de módulo) e não `app/core` (caminho).** As duas
   formas coletam 98,98% nesta máquina; fiquei com a de módulo porque a de
   caminho depende do diretório de trabalho e falha **calada** (0% mais um
   `CoverageWarning: module never imported`) quando ele muda.

Nenhuma violação do escopo travado: nenhum teste do `make test` exige rede,
banco ou chave; não há `skip` nem `retry` mascarando flakiness; o
`--cov-fail-under` não foi baixado; e nenhum arquivo sob `backend/app/` foi
tocado por esta fase.

## 5. Comandos rodados + saídas reais

```text
$ uv run ruff check .          -> All checks passed!
$ uv run mypy app              -> Success: no issues found in 18 source files
$ uv run lint-imports          -> Contracts: 4 kept, 0 broken.

$ uv run pytest -q
Name                   Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------
app/core/__init__.py       0      0      0      0   100%
app/core/chunking.py      58      0     24      1    99%   78->80
app/core/models.py        16      0      0      0   100%
------------------------------------------------------------------
TOTAL                     74      0     24      1    99%
Required test coverage of 90% reached. Total coverage: 98.98%
119 passed, 6 deselected in 5.81s

# AC-25 — sem chave no ambiente
$ env -u GEMINI_API_KEY uv run pytest -q
Required test coverage of 90% reached. Total coverage: 98.98%
119 passed, 6 deselected in 5.89s

# independência de banco: o compose ESTÁ no ar, então a prova é apontar o DSN
# para um endereço inalcançável. Nenhum teste sem marker `db` abre conexão.
$ env -u GEMINI_API_KEY DATABASE_URL='postgresql://ninguem@127.0.0.1:1/x' uv run pytest -q
119 passed, 6 deselected in 6.23s

# o piso de cobertura continua vivo (prova de que o hook só age sob -m db)
$ uv run pytest -q --cov-fail-under=100
FAIL Required test coverage of 100% not reached. Total coverage: 98.98%

$ uv run pytest -m db -q       -> 6 passed, 119 deselected in 0.48s

# ordem embaralhada, 3 execuções, para pegar dependência de ordem
119 passed, 6 deselected      (x3)
```

**Verificações por mutação** — para provar que os testes não são vacuamente
verdadeiros (scripts no scratchpad; o código de produção não foi tocado):

```text
# AC-28: semáforo trocado por Semaphore(2), simulando ausência de lock
com semaforo(1): ['A', 'B']                                  <- o que o teste exige
com semaforo(2): ['A','B','A','B','A','B','A','B','A','B']   <- o teste falharia

# AC-19: sanitize_message neutralizada
com sanitize (esperado False): False
sem sanitize (esperado True) : True                          <- o teste denuncia

# a fixture de log renderizado enxerga o que capture_logs não vê
fixture ve traceback? True     chave visivel na fixture? True
```

## 6. Critérios de aceite da fase (com evidência)

| AC | Teste que prova |
|---|---|
| **AC-1** | `test_upload_de_pdf_valido_responde_202_pendente`; `test_documento_processado_fica_ready_com_os_chunks_registrados` |
| **AC-2** | `test_arquivo_acima_do_limite_declarado_recebe_413`; `test_arquivo_acima_do_limite_sem_content_length_recebe_413` (este exercita o corte duro em `_read_capped`, sem `Content-Length`) |
| **AC-3** | `test_txt_renomeado_para_pdf_recebe_422`; `test_requisicao_sem_campo_file_recebe_422` |
| **AC-4** | `test_pdf_acima_do_limite_de_paginas_termina_failed` |
| **AC-5** | `test_pdf_sem_camada_de_texto_termina_failed` |
| **AC-11** | `test_chunks_gravados_tem_todas_as_colunas_preenchidas`; `test_o_indice_de_chunks_e_hnsw_de_cosseno`; `test_a_dimensao_declarada_no_schema_e_a_que_a_aplicacao_espera` (marker `db`) |
| **AC-12** | `test_pipeline_percorre_pending_processing_e_ready`; `test_progresso_cresce_monotonicamente_ate_o_total`; `test_progresso_nao_avanca_alem_do_ponto_da_falha` |
| **AC-13** | `test_falha_permanente_do_provedor_termina_failed_sem_vazar_chave`; `test_a_chave_nao_aparece_na_mensagem_entregue_ao_usuario` |
| **AC-15** | `test_reenvio_identico_na_mesma_sessao_nao_reprocessa`; `test_mesmo_pdf_em_outra_sessao_gera_documento_proprio`; `test_reenvio_identico_e_reconhecido_pelo_hash_na_mesma_sessao` |
| **AC-17** | `test_documento_inexistente_responde_404_no_envelope`; `test_id_malformado_sai_no_envelope_de_validacao` |
| **AC-18** | `test_ingestao_emite_os_eventos_nomeados_de_44`; `test_todos_os_eventos_da_ingestao_carregam_o_mesmo_request_id`; `test_os_eventos_de_etapa_reportam_duracao_e_documento`; `test_o_documento_id_acompanha_os_eventos_do_pipeline`; `test_falha_de_ingestao_tambem_e_rastreavel_pelo_request_id` |
| **AC-19** | `test_a_chave_nao_aparece_no_log_em_nenhum_caminho_de_erro` (3 casos); `test_a_chave_nao_aparece_na_linha_de_log_renderizada` (3 casos); `test_a_chave_nao_aparece_no_log_quando_a_ingestao_termina_bem` |
| **AC-25** | O gate em si: `env -u GEMINI_API_KEY DATABASE_URL=<inalcançável> uv run pytest -q` → `119 passed`, exit 0 |
| **AC-28** | `test_dois_pipelines_concorrentes_nao_se_intercalam`; `test_semaforo_serializa_mesmo_quando_a_primeira_ingestao_falha` |
| **AC-29** | **Parcial** — a metade de cobertura é gate real (98,98% ≥ 90%). A metade das docstrings **não** tem teste; ver item 3 da §9 |

Coberturas que caíram naturalmente, além do pedido:
`test_um_chunk_nunca_mistura_duas_paginas` (AC-6 pela via da persistência),
`test_falha_inesperada_nao_deixa_o_documento_em_processing` (FR-9),
`test_o_total_embedado_independe_do_tamanho_do_lote` (AC-8).

## 7. Definition of Done da fase

- [x] Testes da fase verdes — 119 offline, 6 sob `db`.
- [x] Comandos de validação limpos — ruff, mypy strict, lint-imports.
      Gates de frontend `[—]` justificados (entregável do Track B).
- [x] Escopo travado respeitado — nenhum teste offline toca rede, banco ou chave.
- [x] Nenhum segredo/PII em log/DTO/exceção — é o objeto de AC-19, provado.
- [x] Commits em pt-BR (Conventional Commits).

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **Esta fase encontrou o vazamento de chave por traceback** (achado idêntico
   ao da A.6, chegado de forma independente) e **não o corrigiu**, por ser código
   de produção fora do escopo. **O orquestrador corrigiu depois**, no commit
   `fa572d4`, com um processador de redação na borda de renderização do log;
   o teste que registrava a lacuna virou asserção real. Ver o relatório da A.6.
2. **`make test-db` só passa por causa do hook no `conftest.py`** (desvio 2). A
   alternativa mais direta é `--no-cov` no `Makefile`; fica a decisão.
3. **AC-29 está coberto pela metade.** "Toda função pública de `core/` e
   `adapters/` tem docstring" foi verificado à mão e está satisfeito, mas **nada
   impede uma regressão**. Uma regra `D` do ruff restrita a esses pacotes
   resolveria; ficou fora porque mexeria na config de lint do projeto inteiro.
4. **AC-2 "através do nginx" não é verificável por teste de API.** O que esta
   fase prova é que a API responde `413` com o envelope. Que o nginx propague
   isso em vez de servir HTML próprio foi medido à mão na A.4 (§9 daquele
   relatório), e tem uma faixa acima de 30 MiB em que o nginx responde HTML.
5. **A NFR-7 (202 em menos de 2 s) não é medida aqui.** Com `ASGITransport` o
   `BackgroundTasks` roda **antes** de o POST retornar, então cronometrar pela
   rota incluiria a ingestão inteira. Não coloquei asserção de relógio para não
   introduzir flakiness; o critério temporal foi verificado à mão na A.4.
