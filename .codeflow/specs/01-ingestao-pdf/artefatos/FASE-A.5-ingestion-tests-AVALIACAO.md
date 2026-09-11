---
spec: 01-ingestao-pdf
fase: A.5
slug_fase: ingestion-tests
tentativa: 1
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: 3901f69..4a3428f
---

# FASE A.5 — Avaliação independente

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

Zero BLOQUEANTES e zero IMPORTANTES. A suíte cumpre o que a fase prometia e o
faz de um jeito que resiste a inspeção adversarial: reproduzi os 119 testes
offline **sem chave, sem banco e com o `DATABASE_URL` apontando para um endereço
inalcançável**, e ainda em duas condições que o executor não testou — com a
`GEMINI_API_KEY` definida no ambiente (o caso de quem for rodar o projeto) e
com variáveis de limite divergentes. Passa nas três.

Também verifiquei por mutação, sem tocar no repositório, que dois dos testes mais
importantes não são vácuos: neutralizando a redação de segredo, o teste de
vazamento falha; neutralizando o semáforo, o teste de concorrência falha.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | 119 offline + 6 sob `db`; piso de cobertura vivo em `pyproject.toml:65`; suíte independente de rede, banco e chave — provado por mim em três ambientes (§6) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | Dublês implementam os `Protocol` **sem herança** (`tests/fakes.py:67,98`), que era o motivo de eles serem protocolos; injeção por `dependency_overrides` (`tests/conftest.py:125-129`) |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | AC-19 verificado com o renderer JSON de produção, não só com o event dict (`conftest.py:175-198`); mutação confirma que a asserção morde (§6) |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `tests/factories.py` da A.2 usada como está; padrão de rota herdado da A.1; nenhum arquivo sob `backend/app/` tocado |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `_env_file=None` em todo `Settings` de teste (`conftest.py:89`) — é o que impede um `.env` na máquina de quem clona de mudar o resultado |
| 6 | Local e nomes dos arquivos | 2 | 5 | Os cinco arquivos previstos na §5, com os nomes previstos |
| 7 | Qualidade de código | 2 | 4 | O hook de cobertura alcança o namespace privado do `pytest-cov` (`conftest.py:51-53`) — funciona, está justificado, mas depende de detalhe interno de uma dependência |
| 8 | Testes e cobertura | 2 | 5 | Cobertura de `app/core` em 98,98% com branch; a escolha de duas fixtures de log (dict e renderizada) é o que dá validade real ao AC-19 |
| 9 | Migration safety | 2 | [—] | Não se aplica |

Média ponderada: 98/100 → **9.8**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **`--no-cov` no `Makefile`, e o hook sai inteiro.** O `pytest_configure` de
  `conftest.py:35-53` zera `cov_fail_under` quando `-m db` é a seleção. Verifiquei
  que funciona (`pytest -m db` sai zero) e que o piso continua vivo em
  `make test` (`--cov-fail-under=100` reprova com 98,98%). Ainda assim, ele lê
  `config.pluginmanager.get_plugin("_cov").options`, que é interno ao
  `pytest-cov`: uma atualização da dependência pode quebrá-lo. A alternativa que
  o próprio relatório oferece — `cd backend && uv run pytest -m db --no-cov` no
  alvo `test-db` — é uma linha e não depende de nada privado.
- **O teste de "falha de rede" da A.3 está no lugar errado da realidade**, e a
  A.5 não tinha como saber: `test_falha_de_rede_e_tratada_como_transitoria` usa
  `OSError`, classe que o cliente real nunca levanta (ver I-1 da avaliação da
  A.3). Quando aquela fase for corrigida, vale um teste aqui que force
  `httpx.ReadTimeout` **pelo pipeline** e afirme que o documento não termina em
  `erro_interno`.
- **A afirmação sobre docstrings do item 3 da §9 está incorreta** (ver §8). Não
  é defeito desta fase — o código é da A.4 —, mas a verificação manual que o
  relatório reporta ter feito não pegou os quatro métodos.
- `FakeRepository.find_by_hash` (`tests/fakes.py:147`) é o único método que não
  passa por `_enter`, então não cede o loop nem aceita falha injetada. Hoje não
  muda nenhum teste; se algum dia alguém quiser testar "o banco cai na checagem
  de duplicata", vai descobrir a assimetria do jeito difícil.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 4a3428f HEAD   -> OK
$ cd backend && uv run ruff check .           -> All checks passed!
$ uv run mypy app                             -> Success: no issues found in 18 source files
$ uv run lint-imports --config .importlinter  -> Contracts: 4 kept, 0 broken.
```

**A prova central da fase, reproduzida por mim (AC-25):**

```text
$ env -u GEMINI_API_KEY DATABASE_URL='postgresql://ninguem@127.0.0.1:1/x' uv run pytest -q
app/core/__init__.py       0      0      0      0   100%
app/core/chunking.py      58      0     24      1    99%   78->80
app/core/models.py        16      0      0      0   100%
TOTAL                     74      0     24      1    99%
Required test coverage of 90% reached. Total coverage: 98.98%
119 passed, 6 deselected in 6.99s
```

**Duas condições que o relatório não cobre e que valem para quem for avaliar o
escopo:**

```text
$ GEMINI_API_KEY="AIza...-do-avaliador" uv run pytest -q
119 passed, 6 deselected in 6.42s

$ GEMINI_API_KEY="x" MAX_UPLOAD_MB=5 CHUNK_SIZE=999 uv run pytest -q
119 passed, 6 deselected in 6.06s
```

A suíte é indiferente ao ambiente — que é exatamente o que `_env_file=None` em
cada `Settings` de teste deveria garantir, e garante.

**Testes de banco, contra um Postgres descartável que subi de `db/001_init.sql`
(container removido ao fim):**

```text
$ uv run pytest -m db -q
6 passed, 119 deselected in 0.77s      (piso de cobertura suspenso pelo hook, como projetado)
```

**Verificações por mutação, escritas por mim, sem tocar no repositório
(plugins de pytest carregados de fora da árvore):**

```text
# redação de segredo neutralizada
=== SEM MUTACAO === 4 passed
=== COM MUTACAO  === FAILED test_chave_nao_vaza_por_excecao_inesperada_no_traceback
                     1 failed, 3 passed

# asyncio.Semaphore neutralizado
FAILED tests/test_ingestion_api.py::test_dois_pipelines_concorrentes_nao_se_intercalam
AssertionError: assert [A, B, A, B, A, B, ...] in ([A, B], [B, A])
```

Ambos os testes falham quando a propriedade que verificam desaparece. É a
diferença entre suíte verde e suíte que protege.

## 7. Itens da fase / DoD não atendidos

Nenhum. O gate de conclusão — `make test` verde sem chave e sem compose, com
cobertura de `core/` ≥ 90%, e `make test-db` verde com o banco no ar — está
integralmente atendido e foi reproduzido por mim.

## 8. Divergências entre o relatório e o código real

1. **§9, item 3: "'Toda função pública de `core/` e `adapters/` tem docstring'
   foi verificado à mão e está satisfeito".** Não está. Varredura por AST:
   `PostgresDocumentRepository.get`, `.set_status`, `.set_totals` e
   `.update_progress` não têm docstring. O defeito é código da A.4 (registrado
   como IMPORTANTE lá); o que diverge aqui é a afirmação de que a verificação
   manual passou.
2. **"38 testes sobre dublês em memória"** no resumo, contra "23 + 15" na tabela
   de arquivos — a soma bate; a contagem por arquivo varia com parametrização.
   Sem consequência.
3. Todo o resto confere: os três desvios declarados (fixture do semáforo, hook de
   cobertura, `--cov=app.core` por nome de módulo) existem no código exatamente
   como descritos, e as três verificações por mutação relatadas na §5 do
   executor são consistentes com as duas que refiz de forma independente.
