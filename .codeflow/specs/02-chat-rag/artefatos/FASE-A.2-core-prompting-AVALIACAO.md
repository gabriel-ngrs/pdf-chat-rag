---
spec: 02-chat-rag
fase: A.2
slug_fase: core-prompting
tentativa: 1
veredito: APROVADO
score: 9.7
threshold: 8.5
range_avaliado: 1d814cfbdc49d5beb624004042bd7d0a8037eaed..604391b091686eb4ad60533f307b2006f0313b60
---

# FASE A.2 — Avaliação independente

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.7 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. A defesa de NFR-8 não é declarada: é
**asserida por posição** (`abertura < injeção < fechamento < instruções`, e o
prompt termina nas instruções), que é a única forma de a ordem não regredir em
silêncio.

**Sobre o desvio de FR-3:** confirmei que FR-3 e AC-3 são logicamente
incompatíveis e que **não existe implementação que satisfaça os dois**. Não é
achado contra a fase — é defeito da spec, endereçado na §5 abaixo e no fecho
conjunto do Track A.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 4 | AC-3/AC-4/AC-9/AC-27 provados (`tests/test_condensation.py:35-46`, `tests/test_prompt.py:72-104`); desconta: o `Passo 1` da fase escreve "menos de 12 palavras" e o código usa 4 (`condensation.py:48`) — divergência inevitável, ver §5 |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `condensation.py` e `prompt.py` importam só `re`, `unicodedata` e `core.models`; contrato `pure-core` KEPT; `condensation` consome `render_history` de `prompt`, sem ciclo |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | NFR-8: `prompt.py:83-87` põe as instruções por último e `ANSWER_INSTRUCTIONS` diz explicitamente que o que está entre marcadores é conteúdo, nunca ordem; `test_prompt.py:94-104` assere as três posições relativas |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Uma única `render_history` serve aos dois prompts do turno (`condensation.py:97`); nenhum tipo duplicado; nenhuma dependência nova |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Marcadores como constante nomeada (`condensation.py:24-37`); normalização NFD + casamento com fronteira de palavra, provado por `test_marcador_nao_dispara_dentro_de_outra_palavra` |
| 6 | Local e nomes dos arquivos | 2 | 5 | Exatamente os quatro arquivos da fase; nada alterado fora dela |
| 7 | Qualidade de código | 2 | 5 | Funções curtas, docstrings de "por quê", o desvio documentado no ponto do código onde ele mora (`condensation.py:42-47`) |
| 8 | Testes e cobertura | 2 | 5 | 22 testes; **100%** de linha e de ramo nos dois módulos (`make check`, §6); determinismo asserido nos dois prompts |

Score = (4·3 + 5·3 + 5·3 + 5·3 + 5·2 + 5·2 + 5·2 + 5·2) / 20 × 2 = **9.7**

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **O desvio de FR-3 está correto; quem precisa mudar é a spec.** Verifiquei a
  incompatibilidade formalmente: FR-3 condensa quando `palavras < 12`; AC-3 exige
  que `"qual o endereço da empresa?"` (5 palavras) **não** condense. Só há
  solução com limiar `≤ 5`; qualquer valor que satisfaça FR-3 reprova AC-3. O
  executor implementou o critério **verificável** (o AC), documentou no código
  (`condensation.py:42-47`) e no relatório, e manteve o ramo anafórico
  literalmente igual à lista de FR-3. É a escolha certa. **Ação para o owner:**
  corrigir o texto de FR-3 via `/create-spec` para "< 4 palavras", senão a spec
  entregue segue autocontraditória — o que um avaliador externo lê como descuido,
  não como decisão.
- **`condensation.py:35` — o marcador `por que` condensa perguntas autocontidas.**
  `"Por que a empresa mudou de sede em 2019 segundo o documento?"` tem 12 palavras
  e nenhuma anáfora, e mesmo assim gasta uma chamada de condensação (o teste
  `test_marcador_e_reconhecido_sem_acento_e_em_qualquer_caixa:55` documenta esse
  comportamento). A lista veio literalmente de FR-3, então a fase está certa; o
  custo é real num teto de ~10 RPM. Vale medir quantos turnos reais isso atinge
  antes de decidir tirar `por que` da lista.
- **`app/core/__init__.py` sem docstring de módulo.** Arquivo vazio, zero
  statements; único ponto de `core/` sem docstring. Cosmético.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 604391b HEAD && echo OK
OK

$ make check
Contracts: 4 kept, 0 broken.
...
app/core/condensation.py      31      0     10      0   100%
app/core/prompt.py            28      0      6      0   100%
Required test coverage of 90% reached. Total coverage: 99.55%
248 passed, 17 deselected in 11.67s
Test Files  10 passed (10) | Tests  75 passed (75)
[exited with code 0]

$ cd backend && uv run pytest tests/test_condensation.py tests/test_prompt.py -q
tests/test_condensation.py ...........                                   [ 50%]
tests/test_prompt.py ...........                                         [100%]
22 passed
```

Auditoria da pureza (o contrato de arquitetura, conferido no arquivo real):

```text
$ grep -n "^import\|^from" backend/app/core/condensation.py backend/app/core/prompt.py
condensation.py:14:import re
condensation.py:15:import unicodedata
condensation.py:17:from app.core.models import Message, MessageRole
condensation.py:18:from app.core.prompt import render_history
prompt.py:19:from app.core.models import Message, MessageRole, RetrievedChunk
```

Docstrings em `core/` (NFR-9), varredura por AST:

```text
$ python3 - (ast.walk sobre app/core/*.py, ignorando nomes com "_")
SEM DOCSTRING: ['app/core/__init__.py (modulo)']
```

Prova de que FR-3 e AC-3 não coexistem (raciocínio conferido contra o texto da
spec, §2 e §3):

```text
FR-3  → condensa se (há histórico) e (palavras < 12 ou marcador)
AC-3  → "qual o endereço da empresa?" (5 palavras, sem marcador) NÃO condensa
        ⇒ exige limiar ≤ 5
        ⇒ nenhum valor satisfaz "< 12" e "≤ 5" ao mesmo tempo
```

## 7. Itens da fase / DoD não atendidos

- **`Passo 1` da fase** pede o limiar em 12 palavras; o código usa 4. É a única
  divergência, é inevitável (§5) e está do lado do AC. Não conto como item não
  atendido da fase, e sim como item a corrigir na spec.
- Todo o resto — `Passos` 2–7, `Testes`, escopo travado, cobertura ≥ 90% —
  atendido com evidência. Os dois módulos ficaram em 100%.

## 8. Divergências entre o relatório e o código real

Nenhuma. O relatório declara o desvio no lugar certo, com a mesma justificativa
que está no código, e as evidências de AC que ele lista existem e passam.
