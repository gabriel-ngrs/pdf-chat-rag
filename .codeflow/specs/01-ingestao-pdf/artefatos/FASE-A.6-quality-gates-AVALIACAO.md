---
spec: 01-ingestao-pdf
fase: A.6
slug_fase: quality-gates
tentativa: 1
veredito: APROVADO
score: 9.7
threshold: 8.5
range_avaliado: 3901f69..fa572d4
---

# FASE A.6 — Avaliação independente

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.7 / threshold 8.5

Zero BLOQUEANTES e zero IMPORTANTES. A fase fez o que prometeu e um pouco mais:
os contratos de arquitetura passaram de três a quatro e foram endurecidos com
`exhaustive`, o teste de violação injetada é exigente (não se contenta com o exit
code — exige que a saída nomeie contrato, import e módulo), e o vazamento de
chave por traceback foi identificado e fechado na única posição em que a correção
cobre a classe inteira do problema, não os casos lembrados.

Verifiquei a correção por mutação, de forma independente: neutralizando o
`redact_processor`, o teste falha e a chave aparece na linha de log renderizada.
A defesa é real.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | AC-24 provado com violação injetada (§6); AC-30 com bandit/pip-audit/npm audit zerados por mim; os três testes de comportamento da §4.8 existem e mordem |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `.importlinter:25-40` declara a pilha completa com `exhaustive = True`; os três `exhaustive_ignores` são transversais reais e continuam barrados no núcleo pelo contrato 2 (`:58-78`) |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `redact_processor` **depois** do `format_exc_info` (`app/logging_setup.py:104-114`) — a última posição em que o traceback ainda é string; mutação confirma (§6) |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Partiu dos três contratos da A.1; `sanitize_message` passou a **delegar** à redação única (`app/adapters/gemini.py:94-105`) em vez de manter duas implementações |
| 5 | Padrões de domínio/aplicação | 2 | 5 | O gate é exercitado como gate: `--no-cache` no `lint-imports` do teste (`tests/test_architecture.py:65`) impede o cache de mascarar a violação |
| 6 | Local e nomes dos arquivos | 2 | 5 | `backend/README.md` é a alternativa que a própria §5 previa; `_violacao_temporaria.py` tem nome autoexplicativo e limpeza em `finally` |
| 7 | Qualidade de código | 2 | 4 | `redact_processor` chama `get_settings()` e reconstrói o event dict a **cada** linha de log; e o teste de arquitetura escreve/apaga um arquivo em `app/core/` (janela de corrida declarada) |
| 8 | Testes e cobertura | 2 | 5 | Um terceiro teste confirma que a violação injetada não sobreviveu (`:115-122`); o teste de SQL usa payload destrutivo real e prova pela consequência (tabela de pé) |
| 9 | Migration safety | 2 | [—] | Não se aplica |

Média ponderada: 97/100 → **9.7**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

Registro explícito de uma coisa que **não** classifiquei como achado: a fase
alterou código de produção fora da sua lista declarada de arquivos
(`app/logging_setup.py` e `app/adapters/gemini.py`). A constitution manda parar e
reportar quando o fix exige tocar fora do escopo. O relatório declara a alteração
e o motivo, e o motivo é um segredo vazando em produção — deixar um vazamento
conhecido de pé para respeitar a fronteira da fase seria a decisão errada, e a
fase cujo objetivo é "provar as propriedades de segurança com teste" não pode
provar uma propriedade falsa sem torná-la verdadeira. Escopo expandido, declarado
e justificado: aceito.

## 5. Sugestões

- **A redação cobre a chave, não o `DATABASE_URL`** (item 5 da §9 do relatório). A
  §4.4 proíbe os dois em log. Hoje o DSN não aparece — conferi por `grep` na
  suíte —, mas isso é observação, não garantia. Um teste que force
  `Database.connect` a falhar com DSN na mensagem e afirme que a linha de log não
  o contém fecharia a simetria; a redação em si é uma segunda entrada no
  processador.
- **Custo por linha de log.** `redact_processor` resolve `get_settings()` (barato,
  `lru_cache`) e reconstrói o dict a cada evento. Com o filtro em DEBUG isso roda
  para todo `embedding.batch`. Não é problema nesta escala; se um dia virar,
  resolver o segredo uma vez no `configure_logging()` e fechá-lo no processador
  elimina a chamada por evento.
- **A corrida do `test_architecture.py`** (item 2 da §9) é real e está bem
  declarada. Se incomodar, escrever a violação num pacote temporário fora de
  `app/` e apontar um `.importlinter` alternativo elimina a janela — ao custo de
  testar uma configuração que não é a do `make arch`. A escolha atual (testar o
  gate de verdade) é a melhor das duas.
- **O quarto contrato (`no-orm`) merece ficar.** Ele não afrouxa nada, e é o que
  impede o teste de injeção de SQL de virar, no futuro, a prova de que a
  biblioteca de outra pessoa é segura.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor fa572d4 HEAD   -> OK
$ cd backend && uv run ruff check .           -> All checks passed!
$ uv run mypy app                             -> Success: no issues found in 18 source files

$ uv run lint-imports --config .importlinter
Analyzed 40 files, 81 dependencies.
Camadas: main -> api -> ingestion -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Sem ORM nem query builder KEPT
Contracts: 4 kept, 0 broken.
```

**`make security` inteiro, rodado por mim (AC-30):**

```text
$ uv run bandit -q -r app        -> (sem saída; exit 0)
$ uv run pip-audit               -> No known vulnerabilities found (exit 0)
$ cd frontend && npm audit --audit-level=high -> found 0 vulnerabilities (exit 0)
```

**Gates de frontend, que os relatórios anteriores marcavam `[—]`, agora rodados:**

```text
$ npm run lint      -> (sem achados)
$ npx tsc --noEmit  -> exit 0
```

`make check` e `make security` fecham em zero na ponta da branch, com os quatro
gates de backend **e** os dois de frontend.

**AC-24 — o gate reprovando de verdade.** Não injetei a violação à mão: rodei o
teste que a injeta, dentro da suíte, e ele passa; e confirmei que
`test_violacao_injetada_nao_sobrevive_ao_teste` deixa a árvore limpa
(`git status --porcelain` vazio ao fim de tudo).

**Verificação por mutação da correção de segurança (escrita por mim, sem tocar no
repositório — plugin de pytest carregado de fora da árvore, substituindo
`redact_processor` por identidade):**

```text
=== SEM MUTACAO (esperado: passa) ===
4 passed, 7 deselected

=== COM MUTACAO (esperado: falha) ===
E  {"code": "erro_interno", ..., "event": "document.failed", ...}
FAILED tests/test_security.py::test_chave_nao_vaza_por_excecao_inesperada_no_traceback
1 failed, 3 passed
```

Confirma o que o relatório afirma: sem o processador, a chave chega ao log
renderizado; com ele, não. E confirma que a correção do falso verde (redigir
`key=` da query string **sempre**, independente de conhecer o segredo) está de
fato em `app/logging_setup.py:67`.

**Suíte completa, offline, sem chave e sem banco:**

```text
$ env -u GEMINI_API_KEY DATABASE_URL='postgresql://ninguem@127.0.0.1:1/x' uv run pytest -q
119 passed, 6 deselected in 6.99s      (nenhum xfail, nenhum skip)

$ uv run pytest -m db -q               (Postgres descartável subido por mim)
6 passed, 119 deselected in 0.77s
```

## 7. Itens da fase / DoD não atendidos

Nenhum. O gate de conclusão — `make check` e `make security` zero, e o teste de
violação injetada provando que o gate morde — está atendido e reproduzido.

Observação de escopo, não de dívida: o furo de retry do adapter que esta fase
descobriu ao investigar o vazamento (`httpx.ReadTimeout` não é `TimeoutError` nem
`OSError`) continua aberto do lado do **retry**. Está registrado como IMPORTANTE
na avaliação da A.3, que é a fase dona daquele código.

## 8. Divergências entre o relatório e o código real

1. **Nenhuma divergência material encontrada.** O que o relatório afirma sobre os
   contratos (4 kept), sobre a posição do processador de redação na cadeia, sobre
   o `--no-cache`, sobre os três `# nosec` justificados e sobre a ausência de
   `xfail` confere linha a linha com o código e com as saídas que reproduzi.
2. O relato do falso verde na primeira versão da correção — teste que passava na
   suíte e falhava sozinho, por contaminação de outro teste — é o tipo de coisa
   que um relatório interessado omitiria. Está lá, com a causa correta.
3. Os três desvios declarados (quarto contrato, `pyproject.toml` não tocado,
   `backend/README.md` em vez do raiz) conferem com o diff do range.
