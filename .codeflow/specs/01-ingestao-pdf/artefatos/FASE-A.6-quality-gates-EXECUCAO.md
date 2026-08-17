---
spec: 01-ingestao-pdf
fase: A.6
slug_fase: quality-gates
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: 3901f69
sha_final: fa572d4
range: 3901f69..fa572d4
---

# FASE A.6 — Relatório de execução

## 1. Resumo do que foi feito

Os princípios invioláveis viraram comandos que falham. Os contratos do
`.importlinter` passaram de 3 para 4, com a pilha de camadas completa e
`exhaustive`, e há um teste que **injeta uma violação e exige que o gate
reprove** — um gate que nunca reprovou nada pode estar mal configurado e
ninguém saberia. Os três testes de segurança provam as propriedades por
comportamento, inclusive o de SQL contra o Postgres real com payload destrutivo.

**Esta fase encontrou um vazamento real de chave de API** (§4), que foi corrigido
no commit `fa572d4` — o teste que o registrava deixou de ser `xfail` e virou
asserção. `make security` sai zero nos três comandos.

> **Nota de execução paralela.** Rodou em paralelo com a `A.5`, no mesmo
> worktree, com propriedade exclusiva de arquivos: esta fase foi dona de
> `.importlinter`, a `A.5` de `pyproject.toml`/`uv.lock`. Por isso os dois
> `sha_inicial` são iguais.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `backend/tests/test_architecture.py` | Os contratos passam; uma violação injetada os reprova; a violação não sobrevive ao teste |
| `backend/tests/test_security.py` | As três propriedades de §4.8, provadas por comportamento |
| `backend/README.md` | O que cada gate garante |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/.importlinter` | Quatro contratos, endurecidos (§4) |
| `backend/app/logging_setup.py` | Processador de redação de segredo na cadeia do structlog (correção do vazamento) |
| `backend/app/adapters/gemini.py` | `sanitize_message` passa a delegar à redação única |
| `backend/tests/test_gemini_adapter.py` | Import de `MIN_SECRET_FRAGMENT` acompanha a função que mudou de casa |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `tests/factories.py` (A.2) gera os PDFs; o padrão de teste
de rota veio da A.1; os contratos partiram dos três que a A.1 escreveu — nada
foi reescrito do zero. `structlog` **já estava** na lista de proibições de
`app.core`, correto desde a A.1.

### 4.1 O que mudou nos contratos — e nada foi afrouxado

- **Camadas.** Era `api → adapters → core`, o que deixava `main`, `ingestion`,
  `config`, `errors` e `logging_setup` fora de qualquer restrição. Agora é
  `main → api → ingestion → adapters → core` via `containers = app`. Isso passa
  a proibir, por exemplo, um adapter chamar `app.ingestion` — inversão que
  tornaria a ingestão inalcançável para teste sem banco. `exhaustive = True`
  faz um módulo novo de primeiro nível **quebrar o gate** em vez de escapar
  dele; verificado empiricamente criando `app/_temp_exhaustive.py` (contrato
  BROKEN). Os três em `exhaustive_ignores` são transversais de verdade —
  `config` não importa nada do app, e `errors`/`logging_setup` são consumidos
  por todas as camadas; empilhá-los seria fingir uma hierarquia inexistente.
  Eles são barrados no núcleo pelo contrato 2.
- **Núcleo puro.** Acrescidos `pypdf`, `pydantic`, `pydantic_settings`,
  `app.ingestion`, `app.main`, `app.config`, `app.errors`, `app.logging_setup`.
  Nenhum quebrou o código: `app/core/` importa hoje só `re`, `dataclasses`,
  `enum` e `app.core.models`.
- **Sem framework de RAG.** Acrescidos `langchain_core`, `langchain_community`,
  `langchain_google_genai`, `langchain_text_splitters`, `langgraph`,
  `llama_index_core`, `haystack`. Motivo concreto: com
  `include_external_packages`, proibir `langchain` **não** pega
  `langchain_core`, que é distribuição de primeiro nível separada — a porta ao
  lado estava aberta.

**Desvio 1 — um quarto contrato, além dos três da §4.8: "Sem ORM nem query
builder"** (`sqlalchemy`, `sqlmodel`, `tortoise`, `peewee`, `databases`). As
docstrings de `repository.py` e `db.py` afirmam que todo SQL é escrito à mão e
parametrizado; isso era uma frase até virar contrato. Com um ORM no meio, o
teste de injeção passaria a provar a segurança da biblioteca, não a deste
projeto. Remover é uma linha, se o avaliador preferir aderência estrita.

**Desvio 2 — `backend/pyproject.toml` não foi tocado**, embora a spec previsse
"config do bandit, se necessário". Confirmado desnecessário: `bandit -q -r app`
sai com zero achados, e o escopo `-r app` do Makefile já resolve o B101 dos
testes. O arquivo também estava reservado à `A.5` nesta rodada.

**Desvio 3 — `backend/README.md` em vez do README raiz.** A spec dizia
"`backend/README.md` (ou seção do README raiz, decidido na FEAT-0002 B.5)". O
README raiz é entregável de outra spec e não foi tocado.

### 4.2 O vazamento encontrado, e como foi fechado

A redação de segredo vivia só no adapter e dependia de a exceção ser de um tipo
previsto: `gemini._request` converte `errors.APIError`, `TimeoutError` e
`OSError`. **Qualquer exceção fora dessa lista escapava com a chave dentro** —
caía no `except Exception: logger.exception(...)` de `run_ingestion`, e o
`format_exc_info` serializava o traceback com a mensagem crua do provedor.

`httpx.ReadTimeout` é o vetor realista: **não** é subclasse de `TimeoutError`
nem de `OSError`, e o `google-genai` fala httpx. Reproduzido:

```text
### APIError ecoando a chave:        KEY_IN_LOG=False   status=failed
### httpx.ReadTimeout com URL:       KEY_IN_LOG=True    status=failed   <- vazou
### RuntimeError crua com a chave:   KEY_IN_LOG=True    status=failed   <- vazou
```

**Correção (commit `fa572d4`, feita pelo orquestrador após esta fase reportar):**
um processador de redação na cadeia do structlog, posicionado **depois** do
`format_exc_info` — a última posição em que o traceback ainda é string
inspecionável — e antes do renderer. Redigir na borda de renderização cobre a
classe inteira do problema em vez dos casos lembrados. `sanitize_message` passa
a delegar à mesma função, para não haver duas implementações divergentes.

Um detalhe da correção merece registro porque quase virou um falso verde: a
primeira versão só redigia quando o segredo configurado era conhecido, e a
redação de `key=` na query string ficava atrás dessa condição. O teste então
**passava na suíte inteira e falhava sozinho**, porque a chave só era conhecida
por contaminação de outro teste. A redação de query string agora roda sempre —
ela não depende de saber qual é a chave.

### 4.3 Outras decisões

- **`--no-cache` no `lint-imports` do teste.** O import-linter guarda o grafo
  entre execuções; com cache, o teste de violação injetada poderia ler a árvore
  anterior e passar verde sobre um código que já não é o do disco.
- **O teste de violação não se contenta com o exit code**: exige que a saída
  nomeie o contrato violado, o import proibido e o módulo. Um gate pode falhar
  por config inválida, e isso não provaria nada.
- **Um terceiro teste confirma que a fixture limpou** o módulo injetado: um
  arquivo esquecido em `app/core/` quebraria todo `make arch` seguinte.
- **O teste de SQL usa payload destrutivo de verdade** (`'; DROP TABLE chunks; --`)
  e afirma que a tabela **continua de pé** depois. É o que separa a prova da
  encenação. Marcado `db`, contra o Postgres real — contra um fake não provaria
  nada sobre parametrização.
- **O teste de travessia troca o cwd por um `tmp_path` vazio** antes do envio:
  se a rota ou a task tocassem o disco, o arquivo nasceria ali. Confere também
  `/etc/passwd` byte a byte antes e depois.
- **A asserção de vazamento recusa qualquer fragmento de 8 caracteres** da
  chave, usando o mesmo limiar da defesa — para não ser mais frouxa que aquilo
  que verifica.

## 5. Comandos rodados + saídas reais

```text
$ uv run ruff check .        -> All checks passed!
$ uv run mypy app            -> Success: no issues found in 18 source files

$ uv run lint-imports --config .importlinter
Analyzed 40 files, 78 dependencies.
Camadas: main -> api -> ingestion -> adapters -> core   KEPT
Nucleo puro: core nao conhece I/O nem framework          KEPT
Sem framework de RAG                                     KEPT
Sem ORM nem query builder                                KEPT
Contracts: 4 kept, 0 broken.
```

**O coração da fase — o gate reprovando a violação injetada:**

```text
$ printf '...\nimport asyncpg\n' > app/core/_violacao_temporaria.py
$ uv run lint-imports --config .importlinter --no-cache
Nucleo puro: core nao conhece I/O nem framework BROKEN
Contracts: 3 kept, 1 broken.

----------------
Broken contracts
----------------
Nucleo puro: core nao conhece I/O nem framework
-----------------------------------------------
app.core is not allowed to import asyncpg:

-   app.core._violacao_temporaria -> asyncpg (l.3)

EXIT=1
```

**Verificação por mutação da correção de segurança:**

```text
# sem o redact_processor na cadeia
FAILED tests/test_security.py::test_chave_nao_vaza_por_excecao_inesperada_no_traceback
  'AIzaSyD-fake-key-para-teste-0123456789' is contained here:
    lo/v1?key=AIzaSyD-fake-key-para-teste-0123456789"}

# com o redact_processor restaurado
1 passed
```

```text
$ uv run pytest -q
119 passed, 6 deselected in 5.81s      (nenhum xfail)
$ uv run pytest -m db -q
6 passed, 119 deselected in 0.48s
$ uv run pytest -q   (ordem embaralhada, 3 execuções)
119 passed, 6 deselected      (x3)

$ make security
uv run bandit -q -r app      -> (sem saída; 0 achados)
uv run pip-audit             -> No known vulnerabilities found
npm audit --audit-level=high -> found 0 vulnerabilities
EXIT=0
```

**No container, com a chave real, após a correção:**

```text
chave completa em log: 0     fragmento de 8 caracteres: 0     linhas com 'key=': 0
ingestão continua funcionando: status ready, 3 páginas, 10 chunks
```

```text
# frontend (lint + tsc) — [—] NÃO RODADO
# Justificativa: frontend/src é entregável do Track B. O `npm audit` do
# make security roda sobre o package-lock.json e foi executado normalmente.
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-24** (`make arch` reprova import proibido) —
  `test_gate_reprova_import_de_asyncpg_dentro_do_core` injeta o módulo e exige
  que a saída nomeie contrato, import e módulo; saída colada acima.
  `test_violacao_injetada_nao_sobrevive_ao_teste` confirma a limpeza.
  `test_arvore_atual_respeita_todos_os_contratos` cobre o caminho positivo.
- [x] **AC-19** (chave nunca em log, em nenhum caminho de erro) —
  `test_chave_nao_aparece_no_log_de_nenhum_caminho_de_erro` (3 casos: 400, 429
  com retry, 500 com esgotamento) mais
  **`test_chave_nao_vaza_por_excecao_inesperada_no_traceback`**, que era a
  lacuna e agora é asserção real, verificada por mutação. Todos com o renderer
  JSON de produção, inspeção byte a byte e recusa de fragmentos de 8 caracteres.
- [x] **AC-30** (`make security` sem achado alto) — bandit 0, pip-audit "No
  known vulnerabilities found", npm audit "found 0 vulnerabilities".
- [x] **SQL parametrizado provado por comportamento** —
  `test_sql_malicioso_nao_e_executado` (marker `db`): quatro payloads, o
  primeiro destrutivo, e a asserção de que `chunks` sobreviveu.
- [x] **Nome de arquivo é nome, não caminho** —
  `test_filename_com_travessia_vira_nome_e_nao_caminho` mais cinco variações
  parametrizadas (`/etc/shadow`, travessia com barra invertida, `$(cat ...)`).

## 7. Definition of Done da fase

- [x] Testes da fase verdes — e **nenhum `xfail` restante** na suíte.
- [x] Comandos de validação limpos — ruff, mypy strict, lint-imports (4/4),
      bandit, pip-audit, npm audit.
- [x] Escopo travado respeitado — **nenhum contrato foi afrouxado**; o único
      `# nosec` do projeto (o jitter da A.3) tem comentário justificando, e os
      dois de `test_architecture.py` também.
- [x] Nenhum segredo/PII em log/DTO/exceção — **agora verdadeiro por
      construção**, não por lista de exceções previstas.
- [x] Commits em pt-BR (Conventional Commits).

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **O quarto contrato (`no-orm`) é adição além da §4.8** (desvio 1). Fica a
   decisão de mantê-lo.
2. **Risco de corrida no `test_architecture.py`:** ele escreve e apaga
   `app/core/_violacao_temporaria.py`. Se rodar exatamente durante um `make
   arch` concorrente, o outro veria o contrato BROKEN por uma fração de segundo.
   A janela é de ~200 ms e a limpeza está em `finally`. Não achei jeito melhor
   sem abrir mão de exercitar o gate de verdade — mas é um custo real de
   paralelismo, e vale saber que existe.
3. **`# nosec B404`/`B603` em `test_architecture.py`** (subprocess), ambos com
   justificativa em comentário. Estão dormentes hoje, porque o bandit só varre
   `app`; ficam prontos caso alguém amplie o escopo.
4. **A correção de segurança chama `get_settings()` a cada evento de log.** É
   cacheado por `lru_cache`, e o caminho comum da redação é linear no tamanho da
   string (a varredura quadrática só roda quando um fragmento é de fato
   encontrado). Ainda assim é trabalho por linha de log, e merece um olhar de
   quem avaliar desempenho.
5. **A redação cobre a chave de API, não o `DATABASE_URL`.** Verifiquei por
   `grep` no container que o DSN não aparece em log hoje, mas isso é
   observação, não garantia — nenhum teste impede que alguém o logue amanhã.
