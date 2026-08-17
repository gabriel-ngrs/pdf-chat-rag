---
spec: 01-ingestao-pdf
fase: A.3
slug_fase: gemini-embeddings
tentativa: 1
veredito: RESSALVAS
score: 8.7
threshold: 8.5
range_avaliado: d6f42d3..06d79614b976d0413a932bad724519ff56faedf3
---

# FASE A.3 — Avaliação independente

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 8.7 / threshold 8.5

Zero BLOQUEANTES. Um achado IMPORTANTE, e é o mais consequente do track: **o
backoff não cobre a classe de falha transitória que o cliente real produz.** O
adapter reclassifica `google.genai.errors.APIError`, `TimeoutError` e `OSError`;
o `google-genai` fala `httpx`, e nenhuma exceção de transporte do `httpx` é
subclasse de qualquer um dos três. Verifiquei: uma `httpx.ReadTimeout` sai crua
do adapter **na primeira tentativa**, sem retry. A FR-6 exige que o transitório
acione backoff — para o transitório que de fato acontece, ele não aciona.

O resto da fase é forte: a verificação contra a API real rodou antes do código e
está registrada, a normalização L2 é provadamente necessária (norma crua 0,589),
e a contagem de vetores é conferida em runtime.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 3 | AC-8, AC-10, AC-13, AC-19 provados; AC-9/FR-6 só valem para `APIError` — `httpx.ReadTimeout` escapa sem retry (`app/adapters/gemini.py:208`, sonda em §6) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `EmbeddingClient` como `Protocol` (`:63`), `l2_normalize`/`backoff_delay`/`sanitize_message` puras e testáveis; SDK confinado no adapter |
| 3 | Segurança / LGPD / multi-tenant | 3 | 4 | `raise ... from None` (`:281`) e sanitização por fragmento; a defesa completa (redação na borda de renderização) só chegou na A.6 — até lá, exceção fora da lista prevista vazava a chave |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `Settings`, `get_logger` e a hierarquia `AppError` reusados; as exceções do provedor herdam das subclasses de §4.3, então **nenhum `code` novo** entra na tabela do frontend |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Chave exigida no uso, não no import (`:257-268`) — é o que mantém `make test` executável sem credencial |
| 6 | Local e nomes dos arquivos | 2 | 5 | `adapters/gemini.py`, `scripts/check_embeddings.py`, `eval/README.md`, `tests/test_gemini_adapter.py` — exatamente a lista da §5 |
| 7 | Qualidade de código | 2 | 5 | `_read_vectors` (`:230-255`) defende contra a falha silenciosa que motivou a fase; docstrings dizem por quê |
| 8 | Testes e cobertura | 2 | 3 | 27 testes bem construídos, **mas** `test_falha_de_rede_e_tratada_como_transitoria` usa `OSError`, classe que o cliente real nunca levanta — o teste prova um caminho inalcançável em produção |
| 9 | Migration safety | 2 | [—] | Não se aplica |

Média ponderada: 87/100 → **8.7**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

### I-1 · O backoff não cobre o erro de transporte real do SDK — `backend/app/adapters/gemini.py:208`

```python
except (TimeoutError, OSError) as exc:
    # Falha de transporte não diz nada sobre o pedido: é transitória.
```

O comentário está certo sobre a intenção e errado sobre o alcance. Medido por
mim:

```text
ReadTimeout            e TimeoutError? False e OSError? False
ConnectError           e TimeoutError? False e OSError? False
ConnectTimeout         e TimeoutError? False e OSError? False
RemoteProtocolError    e TimeoutError? False e OSError? False

levantou httpx.ReadTimeout apos 1 tentativa(s)
e AppError do dominio? NAO — escapou crua
```

Consequências encadeadas, todas reais:

1. **FR-6 não é cumprida** para o transitório que acontece na prática. Uma
   oscilação de rede de um segundo durante a ingestão não é re-tentada.
2. A exceção **não é um `AppError`**, então cai no catch-all de
   `run_ingestion` (`app/ingestion.py:66`) e o documento termina `failed` com
   `erro_interno` — mensagem genérica onde havia mensagem específica disponível.
3. Combinada com o dedup de documento `failed` (achado I-1 da avaliação da A.4),
   o usuário fica **sem caminho de recuperação**: o documento falhou por um
   soluço de rede e o reenvio do mesmo PDF devolve o mesmo documento falho.
4. Foi exatamente esta exceção que a A.6 identificou como vetor de vazamento de
   chave. A A.6 fechou o vazamento (na borda do log); a lacuna de **retry**
   continuou aberta, porque estava fora do escopo dela.

**Correção sugerida** — trocar a captura de transporte por uma que alcance o
cliente real, sem `except Exception` genérico:

```python
import httpx
...
except (TimeoutError, OSError, httpx.TransportError) as exc:
```

`httpx` já é dependência transitiva do `google-genai` e direta do grupo dev.
Acrescentar `httpx.TransportError` mantém a reclassificação explícita que o
escopo travado exige ("não usar `except Exception` sem reclassificar").

**Correção no teste:** `test_falha_de_rede_e_tratada_como_transitoria` deve usar
`httpx.ReadTimeout(...)`, não `OSError`. Como está, ele é verde sobre um caminho
que o SDK nunca percorre — a definição de teste que não protege nada.

## 5. Sugestões

- `sanitize_message` é O(n²) no tamanho do segredo (item 5 da §9 do relatório).
  Depois da A.6, o caminho comum já é linear (`_carries_fragment` filtra antes);
  não mexa.
- A margem estreita medida contra a API real (`cos(gato, cachorro)=0,756` vs
  `cos(gato, mecânica quântica)=0,716`) está bem registrada em
  `backend/eval/README.md` e é o insumo certo para calibrar
  `SIMILARITY_THRESHOLD` na `FEAT-0002`. O default de 0,55 provavelmente está
  baixo demais — mantenha o registro visível para aquela fase.
- `embed_documents` fatia em lotes **e** a `A.4` também fatia antes de chamar
  (`app/ingestion.py:129`). O resultado é correto (`ceil(N/B)` requisições no
  total), mas há duas autoridades sobre o mesmo número. Vale um comentário num
  dos dois lados dizendo qual manda.
- O evento extra `embedding.failed` (desvio 1) é uma boa adição: sem ele, cortar
  o encadeamento com `from None` apagaria toda a diagnosticabilidade do único
  ponto que fala com a rede.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 06d79614... HEAD   -> OK
$ cd backend && uv run ruff check .               -> All checks passed!
$ uv run mypy app                                 -> Success: no issues found in 18 source files
$ uv run lint-imports --config .importlinter      -> Contracts: 4 kept, 0 broken.
$ uv run bandit -q -r app                         -> (sem saída; exit 0)
$ env -u GEMINI_API_KEY DATABASE_URL=<inalcançável> uv run pytest -q
119 passed, 6 deselected in 6.99s
```

**Sonda do transporte real (escrita por mim):**

```text
ReadTimeout            e TimeoutError? False e OSError? False
ConnectError           e TimeoutError? False e OSError? False
ConnectTimeout         e TimeoutError? False e OSError? False
RemoteProtocolError    e TimeoutError? False e OSError? False
levantou httpx.ReadTimeout apos 1 tentativa(s)      <- deveria ter re-tentado até 5
e AppError do dominio? NAO — escapou crua
```

**Verificação por mutação da sanitização (escrita por mim, sem tocar no
repositório — o processador foi neutralizado por um plugin de pytest):**

```text
=== SEM MUTACAO ===  4 passed
=== COM MUTACAO  ===  FAILED tests/test_security.py::test_chave_nao_vaza_por_excecao_inesperada_no_traceback
                      1 failed, 3 passed
```

A defesa de segredo é real: sem ela, o teste denuncia. (A defesa em si é
entregável da A.6; aqui ela conta como confirmação de que a sanitização desta
fase não é decorativa.)

**Verificação contra a API real — `[—]` NÃO REEXECUTADA.** Consome quota e exige
a chave, que o avaliador não deve manipular. O registro em
`backend/eval/README.md` é completo (saída literal, versão do SDK 2.18.1, data,
duas execuções idênticas) e o script `scripts/check_embeddings.py` foi lido: ele
é autocontido, não importa o adapter, e o fallback por `Content` continua no
código caso o provedor mude. É a evidência certa para este tipo de verificação.

## 7. Itens da fase / DoD não atendidos

- **FR-6 / AC-9 parciais** (I-1): o backoff não alcança o transporte real.
- O gate de conclusão ("`check_embeddings.py` passou contra a API real e está
  registrado; testes verdes sem rede; `make check` zero") está atendido.

## 8. Divergências entre o relatório e o código real

1. **"não há `except Exception` sem reclassificar ... `(TimeoutError, OSError)`
   para transporte"** — verdadeiro literalmente, e é justamente aí que está o
   furo: as duas classes escolhidas não interceptam o transporte do cliente
   usado. O relatório apresenta a escolha como cobertura completa.
2. **"27 testes, todos com transporte falso; nenhum toca a rede"** — confere;
   reproduzi a suíte inteira offline.
3. **"nenhuma dependência foi adicionada" e "`pyproject.toml` intocado"** —
   confere com o diff do range.
4. O item 2 da §9 do relatório ("`document_id` chegará pelo contextvars quando a
   A.4 amarrar") foi de fato resolvido pela A.4 — confirmado nos eventos de log
   da suíte de logging.
