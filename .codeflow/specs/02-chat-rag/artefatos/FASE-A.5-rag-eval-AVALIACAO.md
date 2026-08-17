---
spec: 02-chat-rag
fase: A.5
slug_fase: rag-eval
tentativa: 1
veredito: APROVADO
score: 9.4
threshold: 8.5
range_avaliado: 9f0a2b1a512b25f8294edca99971a265552fc355..2e4219f7a6b527a4d3875918f143bd437c6bfdb9
---

# FASE A.5 — Avaliação independente

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.4 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES.

Não pude re-executar `make eval` (esta árvore não tem `.env` e a medição consome
quota real). Em vez de aceitar os números do relatório, **auditei a aritmética**:
recalculei as cinco métricas agregadas, as quatro distribuições e as treze linhas
da varredura de limiar a partir da tabela por pergunta publicada em
`backend/eval/README.md`. **Todas fecham, até a terceira casa** (§6). Os números
são medição, não decoração.

O ponto mais forte da fase é conceitual: `recall@k` foi deliberadamente
construído para **não** depender do limiar, e por isso a varredura mostra o
recall parado enquanto as duas taxas de recusa se movem. É o que quebra a
circularidade que a OQ-10 apontava.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 4 | 12 positivas + 4 negativas + 2 de continuação (`eval/dataset.json`, conferido item a item em §6); seis métricas e saída não-zero (`run_eval.py:815-870`); escopo travado 100% respeitado; desconta: `make eval` "pelado" não roda — exige `EVAL_DOCUMENT_ID` (§5) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | O eval consome o pipeline real — `embed_query` do adapter, `search_chunks` do repositório, `filter_by_threshold`/`take_top_k`/`should_condense`/`fallback_query` de `core/` — em vez de reimplementar; é o que faz a medição medir o sistema |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | Nenhuma chave no dataset nem no script; logs desviados para `stderr` (`run_eval.py:718`) para o `stdout` ficar colável; grep de segredo no diff = 0 |
| 4 | Reusar/espelhar, não duplicar | 3 | 4 | Reuso amplo (acima); desconta: `is_refused` (`run_eval.py:243-252`) reimplementa `filter_by_threshold` + `has_grounding`. A justificativa (tipos diferentes na varredura offline) é boa, mas é a regra de recusa vivendo em dois lugares |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `_rate` devolve 1,0 para grupo vazio, e `meets_nfr7` exige `false_refusal <= 0`, então dataset sem positivas **reprova** em vez de passar por vacuidade; `max(top_k, 3)` para `recall@3` não depender de `RETRIEVAL_TOP_K` (`run_eval.py:845-847`) |
| 6 | Local e nomes dos arquivos | 2 | 5 | `eval/dataset.json`, `eval/run_eval.py`, `eval/README.md` e `.env.example` como a fase manda; `config.py` a mais, mas é o default do próprio número que a fase calibra (§5) |
| 7 | Qualidade de código | 2 | 5 | 877 linhas divididas em funções pequenas com responsabilidade única; `load_dataset` valida estritamente (positiva sem página, negativa com página, grupo faltando → erro, não número bonito) |
| 8 | Testes e cobertura | 2 | 5 | 24 testes determinísticos de `recall@k` e `MRR` com listas conhecidas, sem rede, sem banco, sem chave (`tests/test_eval_metrics.py`); re-executados por mim |

Score = (4·3 + 5·3 + 5·3 + 4·3 + 5·2 + 5·2 + 5·2 + 5·2) / 20 × 2 = **9.4**

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **`make eval` sozinho não roda.** `Makefile:40` chama `python -m eval.run_eval`
  sem argumentos, e o `argparse` recusa por falta de `--document-id`. AC-14 diz
  "quando rodo `make eval`". A saída de erro é limpa e não gasta quota (§6), e a
  variável `EVAL_DOCUMENT_ID` é a saída certa dado que a fase não podia tocar o
  Makefile — mas a `B.5` precisa deixar escrito no README, em uma linha, que a
  invocação é `EVAL_DOCUMENT_ID=<uuid> make eval`. Sem isso o avaliador do
  desafio tenta `make eval`, vê `usage:` e conclui que está quebrado.
- **`backend/app/config.py:45` foi alterado fora da lista de arquivos da fase.**
  Mudar o default de código junto com o `.env.example` é a decisão certa (senão um
  deploy sem `.env` roda com o palpite antigo), e §4.7 lista `config.py` como
  REUSADO. Fica anotado: a lista de "Arquivos alterados" da fase deveria tê-lo
  incluído.
- **`is_refused` duplicada.** Se o corte em `core/retrieval.py` mudar (de `>=`
  para `>`, por exemplo), o eval continuará medindo a regra antiga sem que nada
  falhe. Um teste que compare as duas implementações sobre a mesma lista custa
  três linhas e trava a divergência.
- **A pior positiva (P02, 0,724) é a **página errada**.** O melhor chunk de P02 é
  da página 3, e a página esperada (1) aparece só em segundo. Como o limiar
  trabalha sobre o melhor score independentemente da página — igual à produção —,
  a métrica está correta; mas vale saber que a fronteira inferior da distribuição
  positiva é sustentada por um acerto parcial.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 2e4219f HEAD && echo OK
OK

$ make check
cd backend && uv run mypy app  → Success: no issues found in 23 source files
tests/test_eval_metrics.py ........................                      [ 45%]
Required test coverage of 90% reached. Total coverage: 99.55%
248 passed, 17 deselected in 11.67s
[exited with code 0]

$ cd backend && uv run python -m eval.run_eval
usage: eval.run_eval [-h] --document-id DOCUMENT_ID [--threshold THRESHOLD]
                     [--top-k TOP_K] [--dataset DATASET] [--sweep SWEEP]
eval.run_eval: error: the following arguments are required: --document-id
   (recusa antes de qualquer chamada — nenhuma quota gasta)
```

**Dataset conferido item a item** (não pelo relatório — lendo o JSON):

```text
P01..P10  positive  expected_page 1,1,1,2,2,2,2,3,3,3   history 0
C01       positive  'e a formação?'                page 2  history 2
C02       positive  'e quem mora longe de lá?'     page 3  history 2
N01..N04  negative  expected_page None             history 0
→ 12 positivas (2 de continuação) + 4 negativas = 16 itens
```

O `document_id` do relatório existe no banco, com o número de chunks declarado:

```text
chunks por documento: [('d136750b', 10), ('97959135', 10), ('64e6f8bf', 10)]
                       97959135-49da-4f15-85d9-cfbff1488b3a → 10 chunks ✓
```

**Auditoria aritmética do relatório** — recalculei tudo a partir da tabela por
pergunta de `backend/eval/README.md:177-196`:

```text
ranks das 12 positivas       = [1,2,1,1,1,1,1,1,1,1,1,1]
recall@1  = 11/12            = 0.9167   → relatório 0.917   ✓
recall@3  = 12/12            = 1.0000   → relatório 1.000   ✓
MRR       = (11·1 + 0.5)/12  = 0.9583   → relatório 0.958   ✓

melhores scores positivos    min 0.724  média 9.170/12 = 0.7642  máx 0.808
                             → relatório 0.724 / 0.764 / 0.808   ✓
melhores scores negativos    min 0.476  média 2.027/4  = 0.5068  máx 0.526
                             → relatório 0.476 / 0.507 / 0.526   ✓
todos os chunks (top-5)      positivas min 0.666 máx 0.808 (n=60) ✓
                             negativas min 0.458 máx 0.526 (n=20) ✓

com limiar 0.625:
  falsa recusa   = positivas com melhor < 0.625 = 0/12 = 0.000   ✓
  recusa correta = negativas com melhor < 0.625 = 4/4  = 1.000   ✓

varredura (recalculada linha a linha):
  0.456 → recusa 0/4=0.000 | falsa 0/12=0.000   ✓
  0.487 → recusa 1/4=0.250 | falsa 0/12=0.000   ✓
  0.518 → recusa 2/4=0.500 | falsa 0/12=0.000   ✓
  0.549 → recusa 4/4=1.000 | falsa 0/12=0.000   ✓
  0.735 → recusa 4/4=1.000 | falsa 2/12=0.167   ✓
  0.766 → recusa 4/4=1.000 | falsa 5/12=0.417   ✓
  0.797 → recusa 4/4=1.000 | falsa 11/12=0.917  ✓
  0.828 → recusa 4/4=1.000 | falsa 12/12=1.000  ✓

folga medida = 0.724 − 0.526 = 0.198 ; ponto médio = 0.625   ✓
```

Nenhuma discrepância. As 13 linhas da varredura, as 5 métricas agregadas e as 4
distribuições reconciliam exatamente com os dados por pergunta.

**Não re-executado por mim:** `make eval` contra a API real. Motivo de ambiente,
não de recusa: não existe `.env` nesta árvore (`ls .env` → *No such file*), a
`GEMINI_API_KEY` não está no ambiente, e a execução gastaria quota do owner. Fica
registrado como `[—]` justificado, com a ressalva de que o veredito de NFR-7
apoia-se na saída colada pelo executor — corroborada pela auditoria acima, pelos
24 testes determinísticos das métricas e pela existência do documento medido.

## 7. Itens da fase / DoD não atendidos

- **AC-14, letra da spec:** "quando rodo `make eval`". Roda com
  `EVAL_DOCUMENT_ID` definido; sem ele, recusa. Substancialmente atendido, com a
  sugestão de documentar a invocação (§5).
- `Passos` 1–6 e o critério de conclusão da fase (`make eval` atinge NFR-7,
  `eval/README.md` justifica o limiar com a distribuição medida, `make check`
  zero): atendidos, com a ressalva de reprodutibilidade acima.
- **NFR-7 (item global da §9):** atingido segundo a medição do executor, com a
  aritmética auditada e coerente.

## 8. Divergências entre o relatório e o código real

Nenhuma. As cinco decisões declaradas em §4 do `EXECUCAO` batem com o código:
`--document-id` obrigatório com `EVAL_DOCUMENT_ID` como default
(`run_eval.py:772-785`), `recall@k` independente do limiar
(`run_eval.py:196-209`, e a varredura confirma), condensação por fallback
determinístico (`run_eval.py:397-411`), logs em `stderr` (`run_eval.py:718`), e o
dataset sem a pergunta descartada. O `eval/README.md` diz explicitamente que a
amostra é pequena e que a folga é desta combinação — a honestidade que a fase
prometia entregar está lá.
