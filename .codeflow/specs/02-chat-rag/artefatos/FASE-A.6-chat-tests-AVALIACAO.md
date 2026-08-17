---
spec: 02-chat-rag
fase: A.6
slug_fase: chat-tests
tentativa: 2
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: 77175cdc2cf56544688161fbeb50a28c31591c32..e2b78250d82d3317abefa9359ac2a46d694a6105
---

# FASE A.6 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. O I-1 da tentativa 1 está fechado do jeito
certo: **nenhuma linha de código mudou**, e o que mudou foi a contabilidade. O §3
do relatório deixou de listar `backend/app/chat.py` como arquivo desta fase; a
`A.4` foi reemitida como `tentativa: 2` com o `sha_final` estendido até conter
`8a1c5f0`; e o §4 daqui passou a dizer, com todas as letras, que **o achado é
desta fase e o conserto é da `A.4`**.

Essa é a separação que faltava, e ela vale mais do que parece: o avaliador do
`range` da `A.4` agora encontra o defeito **e** a cura no mesmo intervalo, sem
depender de prosa. Verifiquei a ancestralidade dos dois commits (§6).

A suíte segue sendo o melhor trabalho de teste das duas specs, e as correções da
`A.3` e da `A.4` — 14 testes novos entre unidade e `db` — não tocaram nenhum
arquivo desta fase nem quebraram nenhuma de suas asserções.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | Os doze ACs seguem cobertos e verdes na minha execução; escopo travado agora **inteiro**: os arquivos alterados são só `fakes.py` e `conftest.py`, como a §5 manda (§6) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | A desconexão continua sendo testada consumindo `stream_turn` direto, sem servidor — possível porque `app.chat` não conhece `fastapi`; `Contracts: 4 kept, 0 broken` (AC-24) |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | Injeção do PDF e da pergunta, chave ausente em cinco caminhos de erro **com controle negativo**, SQL como parâmetro, pergunta vazia/gigante em `422` — todos verdes |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Dublês novos estendem os antigos; `journal` compartilhado torna observável a ordem de FR-9, que atravessa dois colaboradores |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Asserção sobre estrutura e sobre o que chegou ao colaborador, nunca sobre texto gerado |
| 6 | Local e nomes dos arquivos | 2 | 5 | `test_chat_api.py` e `test_chat_security.py`; `app/chat.py` saiu da lista e passou a ser da `A.4` |
| 7 | Qualidade de código | 2 | 4 | Desconta: o comentário de `test_chat_api.py:626-630` continua afirmando que `app.chat` **não** chama `aclose()` — o código chama (`chat.py:292`). Segunda vez que aponto (§5) |
| 8 | Testes e cobertura | 2 | 5 | 35 casos da fase intactos; suíte inteira em 262 offline + 19 `db`, `app.core` em 99,55%, `--cov-fail-under=90` não afrouxado (`pyproject.toml` sem diff no range) |

Score = (5·3 + 5·3 + 5·3 + 5·3 + 5·2 + 5·2 + 4·2 + 5·2) / 20 × 2 = **9.8**

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum. O I-1 da tentativa 1 está fechado e verificado.

## 5. Sugestões

- **`backend/tests/test_chat_api.py:626-630` — o comentário desatualizado
  continua lá.** Segunda vez que aponto, e agora ele contradiz também um teste
  novo da `A.4` (`test_stream_fecha_o_iterador_do_provedor_ao_terminar`). O texto
  diz:

  > "`app.chat` não chama `aclose()`, então quem roda o `finally` do gerador […]
  > é o finalizador de async generators do event loop, algumas voltas depois."

  `app/chat.py:292` chama `await _close_stream(stream)` no `finally` desde o
  commit `8a1c5f0` — que é justamente o conserto que esta fase descobriu. O laço
  `for _ in range(5): … await asyncio.sleep(0)` que o comentário justifica é
  código morto: `cliente.closed` já é `True` na primeira volta. Não bloqueia
  nada, mas ensina o oposto do que o código faz, e é barato: trocar o comentário
  por "o `finally` de `_answer` fecha o iterador explicitamente" e substituir o
  laço por `assert cliente.closed`.
- **Nenhum piso de cobertura guarda `app/chat.py` (96%),
  `app/api/conversations.py` (82%) e a metade de chat de `adapters/gemini.py`
  (97%).** Repetida da tentativa 1, e a fase segue tendo razão em dizer que
  ampliar o `--cov-fail-under` mudaria `pyproject.toml`, fora do escopo. Com os
  três números tão altos, ampliar o alvo do gate hoje custaria pouco — é decisão
  do owner, não desta fase.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh \
       .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ §5 estruturalmente válida
EXIT=0

$ git merge-base --is-ancestor e2b7825 HEAD && echo OK
OK
$ git merge-base --is-ancestor 8a1c5f0 e2b7825 && echo "o conserto está no range da A.4"
o conserto está no range da A.4
```

**Escopo da fase, conferido no diff e não no relatório** — os arquivos que o
`range` desta fase toca fora de `.codeflow/`:

```text
$ git diff 77175cd..e2b7825 --stat -- backend/ db/ .env.example
 backend/app/adapters/gemini.py       (A.4: prazo do turno)
 backend/app/adapters/repository.py   (A.3: varredura iterativa)
 backend/app/chat.py                  (A.4: conserto de FR-11, commit 8a1c5f0)
 backend/tests/conftest.py            ← desta fase
 backend/tests/fakes.py               ← desta fase
 backend/tests/test_chat_api.py       ← desta fase
 backend/tests/test_chat_security.py  ← desta fase
 backend/tests/test_gemini_adapter.py (A.4)
 backend/tests/test_retrieval.py      (A.3)
```

O `range` desta fase engloba commits das outras duas porque as três compartilham
o mesmo `sha_final` — é consequência de terem sido reworkadas juntas, não
reivindicação de autoria. O §3 do relatório nomeia só os dois arquivos da fase,
e o §4 atribui `app/chat.py` à `A.4`. É o que resolve o achado.

**Gates, rodados por mim na ponta da branch:**

```text
$ make check
cd backend && uv run ruff check .    → All checks passed!
cd backend && uv run mypy app        → Success: no issues found in 23 source files
Camadas: main -> api -> (chat | ingestion) -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Sem ORM nem query builder KEPT
Contracts: 4 kept, 0 broken.

tests/test_gemini_adapter.py ........................................... [ 60%]
tests/test_retrieval.py .................                                [ 96%]
...
app/core/condensation.py      31      0     10      0   100%
app/core/models.py            40      0      0      0   100%
app/core/prompt.py            28      0      6      0   100%
app/core/retrieval.py         21      0      4      0   100%
Required test coverage of 90% reached. Total coverage: 99.55%
262 passed, 19 deselected in 11.28s

cd frontend && npm run test
Test Files  10 passed (10) | Tests  84 passed (84)
[exited with code 0]

$ make security
bandit -q -r app             → (sem saída)
pip-audit                    → No known vulnerabilities found
npm audit --audit-level=high → found 0 vulnerabilities
SEC=0

$ cd backend && uv run pytest -m db -q   → 19 passed, 262 deselected

$ cd backend && uv run pytest tests/test_chat_api.py -q      → 21 passed
$ cd backend && uv run pytest tests/test_chat_security.py -q → 16 passed
```

**Piso de cobertura não afrouxado:**

```text
$ git diff 77175cd..e2b7825 -- backend/pyproject.toml
(sem diff)
$ grep -n "cov-fail-under" backend/pyproject.toml
70: addopts = "-m 'not db' --cov=app.core --cov-report=term-missing --cov-fail-under=90"
```

**Nenhum `skip`/`xfail` mascarando nada:** a coleta fecha em `262 passed`, sem
linha de `skipped` ou `xfailed`.

## 7. Itens da fase / DoD não atendidos

Nenhum. A lista de arquivos alterados voltou a bater com a §5 da spec, e todos os
demais itens (`Passos` 1–4, doze ACs, `make test` sem chave e sem banco,
cobertura de `core/` ≥ 90%, `make security` zero, `make arch` com os módulos
novos) seguem atendidos com evidência.

## 8. Divergências entre o relatório e o código real

- **Nenhuma.** O §3 e o §4 do `EXECUCAO` descrevem corretamente a nova
  atribuição do commit `8a1c5f0`, e o §8 explica o que mudou nesta tentativa sem
  reivindicar mudança de código que não houve. Os números que ele cola (260
  offline, 19 `db`) são os da árvore que o executor validou; na ponta atual eu
  medi **262 offline** — a diferença são os dois testes de backend que o commit
  `e76fbed`, posterior e do Track B, acrescentou.
- **A incoerência interna apontada na tentativa 1 permanece**, e é a única: o
  comentário de `test_chat_api.py:626-630` contra `app/chat.py:292` (§5). Está
  como sugestão, não como achado — não muda comportamento.

**Nota de perímetro:** o `HEAD` (`e76fbed`) alterou `backend/app/chat.py` e
`backend/tests/test_chat_api.py` — o segundo é arquivo **desta** fase — dentro de
um rework do **Track B**, depois do `sha_final` avaliado aqui. Auditei a
mudança: acrescenta dois testes do turno de retomada (19 → 21 em
`test_chat_api.py`, conferido por mim) e não altera nenhuma asserção existente
desta fase. Não é achado contra a
`A.6`; é a mesma classe de problema que o I-1 fechou, agora vinda do outro track,
e cabe à avaliação do Track B tratá-la.
