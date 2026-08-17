---
spec: 02-chat-rag
fase: A.6
slug_fase: chat-tests
tentativa: 1
veredito: RESSALVAS
score: 9.5
threshold: 8.5
range_avaliado: 77175cdc2cf56544688161fbeb50a28c31591c32..37f27e733d1c1f544858636eed3e6f4fcbd76f5b
---

# FASE A.6 — Avaliação independente

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 9.5 / threshold 8.5

Zero BLOQUEANTES. **Um IMPORTANTE**, e não é sobre a qualidade dos testes — é
sobre o perímetro: a fase alterou `backend/app/chat.py`, código de produção fora
da sua lista de arquivos declarada, para consertar um defeito da `A.4`. A
constitution universal manda **parar e reportar** nesse caso; o executor aplicou
e reportou. O efeito colateral é que o `range` da `A.4` passou a descrever código
quebrado (§4).

A suíte em si é o melhor trabalho de teste das duas specs até aqui. Merecem
registro explícito: o controle negativo nos testes de vazamento (exigir
`[REDACTED]` presente, e não só a chave ausente — sem isso, um log que
simplesmente não registrasse nada passaria provando nada); o uso do
`GeminiChatClient` **real** sobre um SDK falso, que é o único jeito de testar a
sanitização em vez de testar o dublê; e o `journal` compartilhado entre os dois
dublês, que é o que torna a ordem de FR-9 observável — ela atravessa dois
colaboradores e não existe dentro de nenhum deles.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 4 | Os doze ACs da fase cobertos e reconferidos por mim (§6); escopo travado respeitado — nenhuma rede real, nenhum `skip`, nenhuma asserção sobre texto de LLM real, `--cov-fail-under=90` intocado (`pyproject.toml:70` sem diff); desconta: `app/chat.py` alterado fora da lista de arquivos (§4) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | A desconexão é testada consumindo `stream_turn` direto, sem servidor — possível **porque** `app.chat` não conhece `fastapi`; `lint-imports` segue `4 kept, 0 broken` com os módulos novos (AC-24) |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | Injeção vinda do PDF **e** vinda da pergunta (`test_chat_security.py:205,241`); chave ausente em cinco caminhos de erro, com controle negativo; SQL como parâmetro (`:415,441`); pergunta vazia/gigante recusada com `422` (`:462`) |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `FakeEmbeddingClient`, `FakeRepository`, `deterministic_vector`, `build_app`, `captured_logs` consumidos; os dublês novos **estendem** `fakes.py`/`conftest.py` sem tocar nos overrides antigos |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Asserção sobre estrutura e sobre o que chegou ao colaborador, nunca sobre texto gerado; `matches_embedding` faz a ponte "qual query foi buscar" pelo determinismo do dublê (`fakes.py:291-299`) |
| 6 | Local e nomes dos arquivos | 2 | 5 | `test_chat_api.py` e `test_chat_security.py` onde a fase manda; o import entre módulos de teste (o parser de frame SSE) está justificado no docstring e é a alternativa certa a duplicar a leitura do protocolo |
| 7 | Qualidade de código | 2 | 4 | Testes nomeados pelo comportamento, docstrings citando o AC; desconta: o comentário de `test_chat_api.py:569-573` afirma que `app.chat` **não** chama `aclose()` — o código chama (`chat.py:292`), e o laço de espera que segue virou morto (§5) |
| 8 | Testes e cobertura | 2 | 5 | 35 casos coletados, 248 verdes na suíte inteira sem chave e sem banco; `app.core` em 99,55%, piso não afrouxado; `make security` de volta a zero |

Score = (4·3 + 5·3 + 5·3 + 5·3 + 5·2 + 5·2 + 4·2 + 5·2) / 20 × 2 = **9.5**

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

### I-1 — `backend/app/chat.py` foi alterado fora do escopo declarado da fase, e a correção deveria ter sido um rework da `A.4`

A fase declara, na §5 da spec: *"Arquivos novos: `backend/tests/test_{chat_api,chat_security}.py`. **Arquivos alterados:** `backend/tests/{fakes,conftest}.py`"*. O commit `8a1c5f0` alterou também
`backend/app/chat.py` — código de produção, de outra fase.

A constitution universal é explícita nos dois lugares que valem aqui:

> "A IA deve **declarar o escopo antes de modificar qualquer arquivo**. […]
> Modificar fora do escopo declarado exige **parar e reportar**."
>
> Política de falhas — "**Escopo:** o fix exige tocar em algo fora do escopo
> declarado. Ação: **parar imediatamente e reportar**. […] Falhas de Escopo […]
> param na primeira ocorrência. Não há retry."

O executor reconhece a decisão no §9 do relatório e a submete ao avaliador. A
minha leitura, com o benefício da independência: **o achado foi excelente e a
correção é tecnicamente correta**; o que estava errado foi o veículo. O caminho
previsto era devolver o defeito à `A.4` como rework (`tentativa: 2`), porque é o
`range` que este workflow audita.

**A consequência é concreta, não cerimonial.** Auditando o range da `A.4`
(`7fe47de..9f0a2b1`) eu encontro FR-11 quebrado. Só sei que foi consertado
porque o relatório me contou — e "não confiar no relatório" é a razão de este
workflow existir num chat zerado. O argumento de que o rework custaria um ciclo é
verdadeiro; o que ele compra é justamente a propriedade que o pipeline vende.

**Correção sugerida — uma só, e é a mesma do I-1 da `A.4`:** reemitir
`FASE-A.4-chat-endpoint-EXECUCAO.md` como `tentativa: 2` com `sha_final`
estendido até conter `8a1c5f0` (e `3c89162`), movendo para lá o registro da
correção. O `FASE-A.6-...-EXECUCAO.md` passa a citar o achado sem reivindicar a
alteração de produção. **Nenhuma linha de código muda.** Depois disso, as duas
fases voltam para reavaliação em chat zerado.

## 5. Sugestões

- **`backend/tests/test_chat_api.py:569-573` — comentário que contradiz o código
  que a própria fase escreveu.** O comentário diz:

  > "O fechamento do iterador do provedor **não** acontece no `break`: `app.chat`
  > não chama `aclose()`, então quem roda o `finally` do gerador […] é o
  > finalizador de async generators do event loop, algumas voltas depois."

  Mas `app/chat.py:292` chama `await _close_stream(stream)` no `finally` — foi
  precisamente uma das três mudanças do commit `8a1c5f0`, descrita no §4 do
  relatório desta fase como "FR-12 determinístico". Ou seja: o comentário
  descreve o mundo **anterior** ao conserto que a fase fez, e o laço
  `for _ in range(5): ... await asyncio.sleep(0)` que ele justifica virou código
  morto — `cliente.closed` já é `True` na primeira volta. Um leitor futuro
  concluirá que FR-12 depende do event loop, que é o oposto do que o código faz.
  Trocar o comentário por "o `finally` de `_answer` fecha o iterador
  explicitamente" e substituir o laço por uma asserção direta.
- **Nenhum piso de cobertura guarda `app/chat.py`, `app/api/conversations.py` e a
  metade de chat de `adapters/gemini.py`.** A fase levanta isso no §9 e tem razão
  ao dizer que ampliar o `--cov-fail-under` mudaria `pyproject.toml`, fora do
  escopo. Medi hoje: 96%, 82% e 90%. Como não há piso, nada impede que caiam.
  Item para uma decisão do owner, não para esta fase.
- **A lacuna do `GeminiChatClient` (`test_gemini_adapter.py`) está corretamente
  atribuída à `A.4`.** O §9 desta fase a levanta; registrei-a como IMPORTANTE
  lá, não aqui — `test_gemini_adapter.py` não pertence ao escopo desta fase.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 37f27e7 HEAD && echo OK
OK

$ make check
cd backend && uv run ruff check .    → All checks passed!
cd backend && uv run mypy app        → Success: no issues found in 23 source files
cd backend && uv run lint-imports --config .importlinter
Camadas: main -> api -> (chat | ingestion) -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Sem ORM nem query builder KEPT
Contracts: 4 kept, 0 broken.

collected 265 items / 17 deselected / 248 selected
tests/test_architecture.py ...                                           [  1%]
tests/test_chat_api.py ...................                               [  8%]
tests/test_chat_security.py ................                             [ 15%]
...
app/core/condensation.py      31      0     10      0   100%
app/core/models.py            40      0      0      0   100%
app/core/prompt.py            28      0      6      0   100%
app/core/retrieval.py         21      0      4      0   100%
TOTAL                        178      0     44      1    99%
Required test coverage of 90% reached. Total coverage: 99.55%
248 passed, 17 deselected in 11.67s

cd frontend && npm run test
Test Files  10 passed (10) | Tests  75 passed (75)
[exited with code 0]

$ make security
bandit -q -r app             → (sem saída)
pip-audit                    → No known vulnerabilities found
npm audit --audit-level=high → found 0 vulnerabilities
SEC_EXIT=0
```

Verificação de que o piso de cobertura **não** foi afrouxado (escopo travado):

```text
$ git diff dd621eb..37f27e7 -- backend/pyproject.toml
(sem diff)
$ grep -n "cov-fail-under" backend/pyproject.toml
70:addopts = "-m 'not db' --cov=app.core --cov-report=term-missing --cov-fail-under=90"
```

Verificação de que não sobrou `skip`/`xfail` mascarando nada:

```text
$ collected 265 items / 17 deselected / 248 selected
  248 passed  — nenhum "skipped", nenhum "xfailed" na saída
```

O `xfail(strict=True)` citado no §4 do relatório foi mesmo removido; a única
saída com `1 xfailed` que o relatório mostra é a execução **anterior** à
correção, e está identificada como tal.

Confirmação do comportamento que o commit `8a1c5f0` conserta (o AC-12 do lado
`pre_stream`), lida no código e provada pelo teste:

```text
app/chat.py:297   if failure is not None and not parts:
app/chat.py:304       raise failure          → sobe como AppError, vira envelope HTTP
tests/test_chat_api.py:506  test_quota_na_abertura_do_stream_sai_como_http_429 → passa
```

## 7. Itens da fase / DoD não atendidos

- **Lista de arquivos alterados da fase:** `app/chat.py` a mais (§4 I-1).
- Todo o resto atendido com evidência: `Passos` 1–4, os doze ACs, `make test`
  verde sem chave e sem banco, cobertura de `core/` ≥ 90%, `make security` com
  código zero, `make arch` passando com os módulos novos.

## 8. Divergências entre o relatório e o código real

- **Nenhuma divergência de fato.** Cada AC listado na tabela do §6 do relatório
  aponta para um teste que existe e passa; conferi os nomes um a um contra a
  coleta do pytest.
- **Uma incoerência interna, do lado do código:** o relatório afirma, com razão,
  que "o iterador é fechado explicitamente no `finally`" — e o comentário do
  teste que a mesma fase escreveu afirma o contrário (§5). Os dois não podem
  estar certos; o código está do lado do relatório.
