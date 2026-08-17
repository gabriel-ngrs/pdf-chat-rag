---
spec: 01-ingestao-pdf
fase: A.3
slug_fase: gemini-embeddings
tentativa: 2
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: d6f42d3..8cc9eb14ab19faed861817a6e74ef2871b901c52
---

# FASE A.3 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

O achado mais consequente do track está fechado, nos dois lados que ele tinha: o
código passou a reconhecer a falha de transporte que o cliente real produz, e o
teste que era verde sobre um caminho inalcançável passou a exercitar as classes
que o SDK de fato levanta. Medi com a mesma sonda da tentativa 1: onde antes
havia **uma** tentativa e uma exceção crua do `httpx`, agora há **cinco**
tentativas e um erro de domínio com mensagem em pt-BR.

Confirmei também que a captura escolhida cobre a classe inteira, e não só as
exceções que aparecem no teste: `ReadTimeout`, `ConnectError`, `ConnectTimeout`,
`RemoteProtocolError`, `PoolTimeout` e `ProxyError` são todas subclasses de
`httpx.TransportError`.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | FR-6/AC-9 passam a valer para o transitório real (`app/adapters/gemini.py:209`); a reclassificação segue explícita — nada de `except Exception`, que o escopo travado proíbe |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `httpx` declarada como dependência direta em `pyproject.toml:18-22`, com o porquê: importar sem declarar deixaria o retry refém de uma transitiva |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | Sonda: a URL ecoada no `reason` sai como `?key=[REDACTED]`; `from None` preservado; nenhum fragmento sobrevive |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | A correção é uma classe a mais na captura existente; nenhuma estrutura nova de retry |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Transitório continua distinguido de permanente por status, e agora também por classe de transporte |
| 6 | Local e nomes dos arquivos | 2 | 5 | `app/adapters/gemini.py`, `pyproject.toml`, `tests/test_gemini_adapter.py` |
| 7 | Qualidade de código | 2 | 5 | O comentário de seis linhas registra o porquê da classe estar ali — inclusive que ela não é subclasse de `TimeoutError` nem de `OSError`, que é a armadilha |
| 8 | Testes e cobertura | 2 | 4 | O teste passou a ser parametrizado nas classes reais (`tests/test_gemini_adapter.py:215-220`); falta o teste de **nível de pipeline** provando que um transitório não vira `erro_interno` para o usuário |
| 9 | Migration safety | 2 | [—] | Não se aplica |

Média ponderada: 98/100 → **9.8**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **Falta o teste de nível de pipeline.** Os testes novos são todos no adapter.
  O que a cadeia de três fases mostrou é que o dano do achado aparecia **na
  ponta**: transitório virando `erro_interno` genérico e documento morto. Um
  teste em `tests/test_ingestion_api.py` que injete `httpx.ReadTimeout` no
  transporte e afirme que o documento termina com a mensagem específica — não com
  a de falha interna — protege o comportamento que interessa ao usuário. Hoje
  não existe: `grep` por `ReadTimeout`/`TransportError` em
  `test_ingestion_api.py` e `test_logging.py` não devolve nada.
- **Backoff total.** Com cinco tentativas e teto de 8 s, um lote que sofra
  timeouts sucessivos espera até ~20 s antes de desistir, e o semáforo global
  segura a fila inteira nesse período. É o comportamento certo para quota, e
  vale saber que o número existe caso a `FEAT-0002` precise de um teto mais
  curto no caminho do chat.
- A duplicação de autoridade sobre o tamanho do lote ficou **documentada** (quem
  manda é a `A.4`) em vez de removida. Aceito: remover o fatiamento do adapter
  tornaria o `embed_documents` inseguro para quem o chamasse direto.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 8cc9eb14 HEAD  -> OK
$ cd backend && uv run ruff check .           -> All checks passed!
$ uv run mypy app                             -> Success: no issues found in 18 source files
$ uv run lint-imports --config .importlinter  -> Contracts: 4 kept, 0 broken.
$ uv run bandit -q -r app                     -> (sem saída; exit 0)
$ uv run pip-audit                            -> No known vulnerabilities found
$ env -u GEMINI_API_KEY DATABASE_URL='postgresql://ninguem@127.0.0.1:1/x' uv run pytest -q
135 passed, 6 deselected in 10.12s
```

**A sonda da tentativa 1, agora invertida:**

```text
tentativa 1:  levantou httpx.ReadTimeout apos 1 tentativa(s) — escapou crua
tentativa 2:  embedding.retry attempt=1 reason='ReadTimeout: timeout lendo a resposta'
              embedding.retry attempt=2 ...
              embedding.retry attempt=3 ...
              embedding.retry attempt=4 ...
              embedding.failed code=erro_interno status=None
              levantou app.adapters.gemini.EmbeddingProviderError apos 5 tentativa(s)
              e AppError do dominio? InternalError
```

**A cobertura da classe escolhida, conferida por mim (não só as duas que o teste
parametriza):**

```text
ReadTimeout            e TransportError? True
ConnectError           e TransportError? True
ConnectTimeout         e TransportError? True
RemoteProtocolError    e TransportError? True
PoolTimeout            e TransportError? True
ProxyError             e TransportError? True
```

`httpx.TransportError` é a raiz certa: cobre timeout, rede, protocolo e proxy, e
deixa de fora `HTTPStatusError`, que é resposta e já chega como
`google.genai.errors.APIError`.

**Verificação contra a API real — `[—]` NÃO REEXECUTADA**, pela mesma razão da
tentativa 1 (consome quota e exige a chave). O registro em
`backend/eval/README.md` segue válido: o contrato de lote, dimensão e
normalização não foi tocado por este rework.

## 7. Itens da fase / DoD não atendidos

Nenhum. O gate de conclusão está atendido, e a FR-6 agora vale para a classe de
falha que o cliente real produz.

## 8. Divergências entre o relatório e o código real

Nenhuma. A §8 do EXECUCAO descreve a correção, a razão de declarar `httpx` como
dependência direta e a correção do teste exatamente como estão no código. A
afirmação de que o teste antigo "era verde sobre um caminho que o SDK nunca
percorre" é literalmente verdadeira e foi o executor quem a repetiu, sem
suavizar.
