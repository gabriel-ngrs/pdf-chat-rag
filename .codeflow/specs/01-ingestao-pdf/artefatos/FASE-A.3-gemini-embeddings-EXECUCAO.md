---
spec: 01-ingestao-pdf
fase: A.3
slug_fase: gemini-embeddings
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: d6f42d3
sha_final: 06d79614b976d0413a932bad724519ff56faedf3
range: d6f42d3..06d79614b976d0413a932bad724519ff56faedf3
---

# FASE A.3 — Relatório de execução

## 1. Resumo do que foi feito

A verificação contra a API real rodou **antes** de qualquer código de produção,
como a spec exige, e respondeu a pergunta que motivava a fase: o
`gemini-embedding-001` devolve **um vetor por texto** quando os textos vão
direto na lista `contents` — não foi preciso embrulhar em `Content`. A mesma
execução produziu uma descoberta que confirma o contrato: o vetor de 768
dimensões chega com **norma L2 de 0,589**, ou seja, **não normalizado**. Sobre
isso foi construído o `GeminiEmbeddingClient`: lotes, `task_type` assimétrico,
normalização L2, backoff com jitter, `400` permanente e sanitização de chave.

> **Nota de execução paralela.** Esta fase rodou em paralelo com a `A.2` (ambas
> dependem só da `A.1`), no mesmo worktree, com propriedade exclusiva de
> arquivos por fase. A `A.2` foi dona de `app/errors.py`; esta fase não o tocou.
> Por isso os dois `sha_inicial` são iguais (`d6f42d3`) e os ranges se sobrepõem
> — o commit de código desta fase é `06d7961` e o da `A.2` é `a6438f8`, sem
> interseção de arquivos.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `backend/scripts/check_embeddings.py` | Verificação do contrato de embedding contra a API real: lote, dimensão, normalização e coerência de similaridade. Autocontido — não importa o adapter, para não validar o código com o próprio código |
| `backend/app/adapters/gemini.py` | Protocolo `EmbeddingClient`, implementação `GeminiEmbeddingClient`, as funções puras `l2_normalize` / `sanitize_message` / `backoff_delay` e as exceções do provedor |
| `backend/tests/test_gemini_adapter.py` | 27 testes, todos com transporte falso; nenhum toca a rede |
| `backend/eval/README.md` | Registro da verificação contra a API real, com a saída literal e o que ficou provado |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/eval/.gitkeep` | **Removido** — a pasta ganhou conteúdo, conforme §4.9 ("REMOVIDO") |

Nenhum outro arquivo foi alterado. `app/errors.py`, `pyproject.toml` e
`logging_setup.py` ficaram intocados por esta fase.

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `Settings`/`get_settings` de `app/config.py` (A.1),
`get_logger` de `app/logging_setup.py` (A.1), e a hierarquia `AppError` de
`app/errors.py` (A.1) — reusada, não duplicada. `google-genai` já estava no
`pyproject.toml`; **nenhuma dependência foi adicionada**.

**Decisões de design.**

1. **As exceções do provedor nascem em `gemini.py` e herdam das subclasses de
   §4.3, não de `AppError` direto.** `MissingApiKeyError`, `EmbeddingPayloadError`
   e `EmbeddingProviderError` herdam de `InternalError` (`erro_interno`/500);
   `EmbeddingQuotaError` herda de `RateLimitError` (`limite_de_uso`/429).
   Consequência importante: **esta fase não cria nenhum `code` novo** — tudo sai
   com um dos cinco códigos de §4.3, e a tabela do `errors.ts` da B.2 continua
   completa. *Por que não em `app/errors.py`:* a `A.2` rodou em paralelo e era a
   dona daquele arquivo; além disso são detalhe deste adapter.
2. **`raise ... from None` em toda falha do provedor.** Encadear a exceção
   original faria qualquer `logger.exception` acima imprimir o traceback com a
   mensagem crua do provedor, que pode conter a chave. Há asserção de
   `__cause__ is None` no teste ponta a ponta.
3. **Sanitização por fragmento, não só pela chave inteira.** `sanitize_message`
   redige a chave e qualquer substring dela com 8 caracteres ou mais, e um regex
   cobre `key=` / `api_key=` em URL ecoada. Meia chave em log já é vazamento.
4. **Contagem de vetores conferida em runtime** (`_read_vectors`), mesmo já
   tendo sido verificada contra a API real: se o provedor mudar o comportamento
   de lote, o sistema para em vez de gravar vetores desalinhados dos chunks.
   Esta é a defesa contra a falha silenciosa que o script foi investigar.
5. **Chave exigida só quando o cliente real precisa ser construído** (`_models()`,
   preguiçoso). Com cliente injetado a chave não é tocada, o que mantém a suíte
   offline. Sem cliente e sem chave: `MissingApiKeyError` em pt-BR.
6. **`sleep`, `max_attempts` e `rng` entram pelo construtor**, para o teste de
   backoff exercitar o crescimento e o teto sem esperar de verdade.
7. **Interface síncrona**, como a spec define. **A `A.4` deve chamá-la via
   `asyncio.to_thread`**, como já precisa fazer com o `pypdf`.

**Desvios da spec — dois, declarados.**

1. **Um evento de log a mais que a tabela de §4.4: `embedding.failed`** (warning,
   com `reason` já sanitizado, `status` e `code`). É consequência direta da
   decisão 2: cortar o encadeamento apagaria toda a diagnosticabilidade do único
   ponto do sistema que fala com a rede. A §4.4 não se declara exaustiva, e o
   `document.failed` da `A.4` continua sendo o evento de nível de pipeline.
2. **`# nosec B311` na linha do `random.Random()`.** O bandit sinaliza gerador
   não-criptográfico; o sorteio só espalha o jitter do backoff, não gera segredo
   nem token. Há comentário justificando na linha anterior, como o escopo travado
   da `A.6` exige ("não adicionar `# nosec` sem comentário justificando"). Rodei
   `bandit` já nesta fase porque o achado era meu.

**Desvio previsto que NÃO se materializou:** `google.genai` publica `py.typed`,
então `mypy --strict` passou **sem nenhum `# type: ignore`** em `app/` e sem
tocar no `pyproject.toml`.

Nenhuma violação do escopo travado: a chave não é logada nem em fragmento, não
há uma requisição por chunk (é `ceil(N/B)`), não há `except Exception` sem
reclassificar (as capturas são `errors.APIError`, reclassificada por status, e
`(TimeoutError, OSError)` para transporte), o retry tem teto, e **não há pool de
chaves**.

## 5. Comandos rodados + saídas reais

### 5.1 Verificação contra a API real (passo 1 da fase)

```text
$ cd backend && uv run python scripts/check_embeddings.py      # exit 0
modelo: gemini-embedding-001 | output_dimensionality: 768 | task_type: RETRIEVAL_DOCUMENT
[lista de strings] vetores devolvidos: 3 (esperado: 3)
[lista de strings]   vetor 0: dimensão=768
[lista de strings]   vetor 1: dimensão=768
[lista de strings]   vetor 2: dimensão=768
estratégia usada: lista de strings
norma L2 crua do vetor 0     = 0.589191
cos(gato, cachorro)          = 0.756068
cos(gato, mecânica quântica) = 0.715598
OK: lote devolve um vetor por texto e a similaridade é coerente.
```

Saída idêntica em duas execuções seguidas. `google-genai` resolvido: 2.18.1.
Registro completo em `backend/eval/README.md`.

### 5.2 Gates (verificação independente do orquestrador, após A.2 e A.3 juntas)

```text
# lint — uv run ruff check .
All checks passed!

# type-check — uv run mypy app
Success: no issues found in 15 source files

# arquitetura — uv run lint-imports --config .importlinter
Camadas: api -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Contracts: 3 kept, 0 broken.

# testes da fase — uv run pytest tests/test_gemini_adapter.py -q
...........................                                              [100%]
27 passed in 0.65s

# suíte inteira (A.1 + A.2 + A.3) — uv run pytest -q
....................................................................     [100%]
68 passed in 3.37s

# prova de suíte offline — env -u GEMINI_API_KEY uv run pytest -q
....................................................................     [100%]
68 passed in 2.54s

# segurança estática — uv run bandit -q -r app
(sem saída — 0 achados; exit 0)

# frontend (lint + tsc) — [—] NÃO RODADO
# Justificativa: frontend/src é entregável do Track B, em execução paralela em
# outra branch. Mesma justificativa das fases A.1 e A.2.
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-8** (`ceil(N/B)` requisições) —
  `test_faz_ceil_de_n_sobre_b_requisicoes`, parametrizado em (10,4)→3,
  (16,16)→1, (17,16)→2, (1,16)→1, (48,16)→3; confere também que a soma dos
  textos por chamada é igual a N. Complemento:
  `test_lista_vazia_nao_chama_o_provedor`.
- [x] **AC-9** (`429` faz backoff e conclui; `400` não repete) —
  `test_429_na_primeira_chamada_aciona_backoff_e_conclui` (2 chamadas, 1 sleep
  maior que zero, evento `embedding.retry` warning com `attempt=1` e `reason`) e
  `test_400_de_payload_nao_repete_e_falha_com_mensagem_propria` (1 chamada, zero
  sleeps, `EmbeddingPayloadError`). Reforços:
  `test_429_persistente_esgota_as_tentativas_e_vira_erro_de_quota` (teto
  respeitado — prova de que não há retry infinito),
  `test_falha_de_rede_e_tratada_como_transitoria`,
  `test_erro_permanente_de_credencial_nao_repete`,
  `test_backoff_cresce_e_respeita_o_teto`.
- [x] **AC-10** (norma L2 = 1,0 com tolerância 1e-6; `task_type` distintos) —
  `test_vetores_saem_com_norma_l2_um` (documentos e query),
  `test_normalizacao_e_pura_e_preserva_direcao`,
  `test_vetor_nulo_nao_passa_como_normalizado`,
  `test_task_type_distinto_entre_documento_e_pergunta`
  (`RETRIEVAL_DOCUMENT` vs `RETRIEVAL_QUERY`),
  `test_toda_requisicao_pede_a_dimensao_do_contrato` (768 e o modelo do
  contrato). **Evidência externa de que a normalização é obrigatória:** a norma
  crua medida contra a API real foi 0,589191.
- [x] **AC-13** (falha permanente vira erro em pt-BR sem chave na mensagem) —
  `test_chave_nao_aparece_na_excecao_nem_no_log`: o provedor falso ecoa a chave
  em texto e em URL, e o teste assere sobre `str`, `repr` e `__cause__ is None`.
  `test_chave_ausente_falha_com_erro_de_dominio_em_pt_br`.
- [x] **AC-19** (chave nunca no log, em nenhum caminho de erro) — função
  isolada: `test_sanitiza_a_chave_inteira`, `test_sanitiza_fragmento_da_chave`,
  `test_sanitiza_a_chave_na_query_string_da_url`,
  `test_sanitizacao_nao_mutila_texto_sem_segredo`. Ponta a ponta:
  `test_chave_nao_aparece_na_excecao_nem_no_log` e
  `test_chave_nao_aparece_no_log_de_retry` (grep da chave e do prefixo de 8
  caracteres no `repr` de todas as entradas de log capturadas).
- [x] **`embed_query` implementado e testado, não é stub** — exercitado em
  `test_task_type_distinto_entre_documento_e_pergunta` e em
  `test_vetores_saem_com_norma_l2_um`. A fase de eval da `FEAT-0002` não fica
  bloqueada por método não validado.
- [x] **Verificação contra a API real registrada** — `backend/eval/README.md`,
  com saída literal, versão do SDK e data.

Extra, fora dos ACs mas central à fase: `test_resposta_agregada_e_recusada` — o
modo de falha que o script foi investigar está coberto por teste, e não apenas
por uma verificação manual de uma vez só.

## 7. Definition of Done da fase

- [x] Testes da fase verdes — 27 passando, nenhum toca a rede.
- [x] Comandos de validação limpos — ruff, mypy strict, lint-imports e bandit
      zerados. Gates de frontend `[—]` justificados.
- [x] Escopo travado respeitado — nenhuma violação BLOQUEANTE da §5.
- [x] Nenhum segredo em log/DTO/exceção — provado por teste, não afirmado.
- [x] Commits em pt-BR (Conventional Commits).

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **`embedding.batch` é `debug` e o `configure_logging()` da A.1 filtra em
   `info`.** Em produção o evento não sai com a configuração atual. A §4.4 define
   o nível como debug, então o adapter está correto; mas quem quiser ver o
   evento precisa baixar o filtro. Não toquei em `logging_setup.py` (fora do
   escopo desta fase). **Vale uma decisão explícita do avaliador**, porque o
   AC-18 pede que a ingestão emita eventos "para cada lote de embedding" — se o
   avaliador exigir esse evento visível, ou o nível muda, ou o filtro muda.
2. **`document_id` não aparece nos eventos deste adapter**, porque o adapter não
   o conhece. A §4.4 lista `document_id` em `embedding.batch` e
   `embedding.retry`; ele chegará pelo `contextvars` do structlog quando a `A.4`
   amarrar o contexto. **Isso é trabalho da A.4 e ainda não está feito** — se a
   A.4 não amarrar, o AC-18 não fecha.
3. **A margem de similaridade medida é estreita: 0,0405.** `cos(gato, mecânica
   quântica) = 0,7156` mostra que, neste modelo, similaridade alta em absoluto
   não significa relevância. Não é problema desta fase, mas o
   `SIMILARITY_THRESHOLD=0.55` default provavelmente está **baixo demais** e
   precisa de calibração empírica na `FEAT-0002`. Registrado no
   `eval/README.md`.
4. **Não foi criada factory de injeção** (`get_embedding_client()`). A `A.4`
   instancia `GeminiEmbeddingClient(get_settings())` diretamente, ou acrescenta
   um provider de dependência no arquivo dela.
5. **`sanitize_message` é O(n²) no tamanho da chave** (varre todos os
   comprimentos de fragmento). Para uma chave de ~40 caracteres é irrelevante, e
   só roda em caminho de erro — mas é uma escolha de robustez sobre desempenho
   que merece um olhar.
