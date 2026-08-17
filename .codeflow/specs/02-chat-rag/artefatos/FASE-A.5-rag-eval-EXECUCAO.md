---
spec: 02-chat-rag
fase: A.5
slug_fase: rag-eval
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: 9f0a2b1a512b25f8294edca99971a265552fc355
sha_final: 2e4219f7a6b527a4d3875918f143bd437c6bfdb9
range: 9f0a2b1..2e4219f
---

# FASE A.5 — Relatório de execução

## 1. Resumo do que foi feito

O retrieval passou a ser **medido**. `eval/dataset.json` traz 12 perguntas positivas —
duas delas de continuação — e 4 negativas comprovadamente fora do documento.
`eval/run_eval.py` recebe um `document_id` já ingerido, embeda cada pergunta uma única
vez e reporta as seis métricas de FR-13, com saída não-zero abaixo dos pisos de NFR-7. O
`SIMILARITY_THRESHOLD` deixou de ser palpite: passou de `0,55` para **`0,625`**, o meio
da folga medida entre a negativa mais alta (0,526) e a positiva mais baixa (0,724).

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `backend/eval/dataset.json` | 12 positivas (P01–P10, C01–C02) + 4 negativas (N01–N04) |
| `backend/eval/run_eval.py` | O eval: métricas, relatório colável, varredura de limiar |
| `backend/tests/test_eval_metrics.py` | 24 testes offline de `recall@k` e `MRR` |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/eval/README.md` | +232 linhas: método, dataset, relatório medido, varredura, justificativa do limiar, limitações |
| `.env.example` | `SIMILARITY_THRESHOLD` 0,55 → 0,625, com o porquê medido |
| `backend/app/config.py` | Mesmo valor no default de código, para não divergir do `.env.example` |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** O eval consome `embed_query` do adapter real, `search_chunks` do
repositório e `filter_by_threshold`/`take_top_k` de `core/retrieval.py` — não
reimplementa nenhum passo do pipeline, o que é o que torna a medição uma medição do
sistema e não de uma cópia dele. `should_condense` e `fallback_query` vêm de
`core/condensation.py`. O alvo `make eval` já existia no Makefile e não foi tocado.

**Decisões:**

- **`--document-id` obrigatório, com `EVAL_DOCUMENT_ID` aceito como default.** O alvo
  `make eval` roda `python -m eval.run_eval` sem argumentos e o `make` não repassa flags;
  aceitar a variável é o que torna `EVAL_DOCUMENT_ID=<uuid> make eval` executável sem
  editar o Makefile (fora do escopo desta fase). Sem flag **e** sem variável, o argparse
  recusa — o PDF nunca é reingerido por conveniência.
- **`recall@k` é independente do limiar, de propósito.** Ele mede **ordenação**; quem
  mede o limiar são as duas taxas de recusa. É isso que quebra a circularidade apontada
  na OQ-10: na varredura de limiar o recall não se move.
- **A condensação usada no eval é o fallback determinístico**, não a reescrita por LLM.
  Sem quota e sem variância entre execuções. O efeito medido é, por isso, um **piso**:
  a condensação real da `A.4` tende a ser melhor que a concatenação.
- **Logs do pipeline vão para `stderr`**, para que `stdout` fique só com o markdown
  colável — o requisito de "formato colável no README" não sobrevive a `embedding.batch`
  no meio das tabelas.
- **"RAG evita alucinação" não virou pergunta positiva.** O tema aparece nas páginas 2 e
  3; mediria desempate, não retrieval.

Nenhum desvio do escopo travado: o eval não entrou em `make check`, nenhuma chave foi
commitada, o dataset não foi ajustado para inflar métrica, o limiar não foi otimizado por
recall, e o PDF foi ingerido uma única vez.

## 5. Comandos rodados + saídas reais

```text
$ cd backend && uv run ruff check .
All checks passed!

$ uv run mypy app
Success: no issues found in 23 source files

$ uv run mypy eval
Success: no issues found in 1 source file

$ uv run pytest tests/test_eval_metrics.py -p no:cacheprovider --no-cov -q
........................
24 passed in 0.04s

$ uv run lint-imports --config .importlinter
Contracts: 4 kept, 0 broken.

$ uv run pytest -p no:cacheprovider -q          # suíte inteira, offline
Required test coverage of 90% reached. Total coverage: 99.55%
213 passed, 17 deselected in 9.78s
```

### `make eval` com a configuração final

`document_id` = `97959135-49da-4f15-85d9-cfbff1488b3a` (10 chunks do `Exemplo-YAITEC.pdf`,
ingerido **uma vez**).

```text
- RETRIEVAL_TOP_K: 5 | SIMILARITY_THRESHOLD: 0.625
- itens: 16 (12 positivas, 4 negativas)

| métrica                             | valor | piso NFR-7 | situação |
|-------------------------------------|-------|------------|----------|
| recall@1 (positivas)                | 0.917 | —          | —        |
| recall@3 (positivas)                | 1.000 | ≥ 0.80     | ok       |
| MRR (positivas)                     | 0.958 | ≥ 0.70     | ok       |
| taxa de recusa correta (negativas)  | 1.000 | 1.00       | ok       |
| taxa de falsa recusa (positivas)    | 0.000 | 0.00       | ok       |

Distribuição de similaridade, por grupo:
| conjunto                            | n  | mín   | média | máx   |
|-------------------------------------|----|-------|-------|-------|
| positivas — melhor chunk            | 12 | 0.724 | 0.764 | 0.808 |
| negativas — melhor chunk            |  4 | 0.476 | 0.507 | 0.526 |
| positivas — todos os chunks do top-k| 60 | 0.666 | 0.733 | 0.808 |
| negativas — todos os chunks do top-k| 20 | 0.458 | 0.498 | 0.526 |

NFR-7 ATINGIDO com SIMILARITY_THRESHOLD=0.625.
EXIT=0
```

### A métrica pode falhar

```text
$ uv run python -m eval.run_eval --document-id 97959135-… --threshold 0.80
**NFR-7 NÃO ATINGIDO** com SIMILARITY_THRESHOLD=0.800.
EXIT=1
```

### Efeito medido da condensação

| id | página esperada | query crua | rank cru | query condensada | rank condensado |
|---|---|---|---|---|---|
| C01 | 2 | "e a formação?" | **4** | "Quem fundou a YAITEC? e a formação?" | **1** |
| C02 | 3 | "e quem mora longe de lá?" | 1 | "Onde o time da YAITEC se reúne? e quem mora longe de lá?" | 1 |

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-14 (seis métricas + falha com saída não-zero)** — as cinco métricas agregadas
  e a distribuição por grupo estão coladas acima; `--threshold 0.80` sai com `1`.
- [x] **NFR-7** — `recall@3 = 1,000` (≥ 0,80), `MRR = 0,958` (≥ 0,70), recusa correta em
  **todas** as negativas, falsa recusa **zero**.
- [x] **Limiar justificado pela distribuição** — negativa máxima 0,526 × positiva mínima
  0,724; folga de 0,198; ponto médio 0,625, com ~0,10 de margem para cada lado. A
  varredura mostra que o intervalo válido é 0,527–0,724, e que 0,55 (o valor anterior)
  passava por **0,024** de margem — por sorte, não por desenho.
- [x] **`recall@3` e não `@5`** — medido: nas 12 positivas o top-5 já contém a página
  certa em 12/12, então `recall@5` seria 1,000 **por construção** e não poderia falhar.
- [x] **Teste unitário determinístico de `MRR` e `recall@k`** — `tests/test_eval_metrics.py`,
  24 testes com listas conhecidas, sem rede, sem banco e sem chave.
- [x] **Ao menos uma pergunta de continuação** — C01 e C02; C01 sobe da 4ª para a 1ª
  posição quando a pergunta é resolvida.

## 7. Definition of Done da fase

- [x] `make eval` roda e reporta as seis métricas; NFR-7 atingido
- [x] `backend/eval/README.md` justifica o limiar com a distribuição medida
- [x] `make check` zero (suíte offline verde, cobertura 99,55%)
- [x] Escopo travado respeitado: eval fora do `make check`, sem chave no dataset, sem ajuste do dataset para inflar métrica, sem otimizar o limiar só por recall, sem reingestão do PDF
- [x] Commit em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

- **A amostra é pequena.** 12 positivas num documento de 3 páginas e 10 chunks:
  `recall@3 = 1,000` significa "nenhuma das 12 falhou", não "retrieval perfeito". Está
  escrito com essas palavras no `eval/README.md`.
- **A busca densa borra termo exato**, e isso apareceu na medição: na P08 (e-mail de
  contato) o primeiro lugar ganha por 0,001, e na P02 a página que só **cita** "agentes
  SQL" passou na frente da que o descreve. É exatamente o sintoma que a fase opcional
  `A.7` (fusão RRF) existe para tratar.
- **O `.env` local do worktree continua com `SIMILARITY_THRESHOLD=0,55`** — o arquivo é
  protegido pela constitution e não foi tocado. `.env.example` e o default do código
  estão em 0,625; quem já tem `.env` precisa sincronizar.
- **O eval mede o retrieval, não a resposta.** Fidelidade da geração (a resposta usa
  mesmo o trecho recuperado?) não é medida aqui e não estava no escopo da fase.
