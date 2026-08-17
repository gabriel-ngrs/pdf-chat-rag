---
spec: 01-ingestao-pdf
fase: A.4
slug_fase: ingestion-pipeline
tentativa: 2
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: a3a775c..8cc9eb14ab19faed861817a6e74ef2871b901c52
---

# FASE A.4 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

Os dois achados IMPORTANTES estão fechados e a sugestão S-1 foi implementada com
uma ressalva honesta que vale mais que o próprio guarda. Verifiquei o reenvio
ponta a ponta pela rota real (mesmo id, `error_message` limpa, reprocessamento
efetivo) e por mutação (removendo a condição de status, o teste falha exatamente
na asserção certa).

Encontrei **um defeito novo**, introduzido pela correção: dois reenvios
simultâneos do mesmo documento `failed` duplicam os chunks no Postgres. Ele é uma
corrida, exige dois POST concorrentes, e o dublê da suíte não consegue vê-lo —
está em §5 com evidência e correção, classificado como sugestão pelas razões que
explico ali, não por dúvida sobre sua realidade.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | Reenvio reprocessa (`app/api/documents.py:133-146`) e AC-15 continua valendo para `ready` — a contrapartida está testada; AC-29 fechado (varredura por AST em §6) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `reset_for_retry` entrou no protocolo e na implementação, e o dublê o implementa sem herança; `lint-imports` 4/4 |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `_RESET_FOR_RETRY_SQL` e `_DELETE_CHUNKS_SQL` parametrizados; a limpeza de chunks e o reset acontecem na **mesma transação** (`repository.py:209-222`) |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | O guarda de zero chunks importa `NO_TEXT_MESSAGE` do adapter em vez de repetir o texto (`app/ingestion.py:17`) |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Reaproveitar a linha em vez de criar outra é a decisão certa: `UNIQUE (session_id, content_hash)` impediria a segunda, e o usuário espera "o mesmo documento" |
| 6 | Local e nomes dos arquivos | 2 | 5 | Alterações contidas em `documents.py`, `repository.py`, `ingestion.py` e nos testes correspondentes |
| 7 | Qualidade de código | 2 | 4 | Docstrings novas dizem o quê e por quê; desconto pela janela de corrida do reset (§5, S-1) |
| 8 | Testes e cobertura | 2 | 5 | Cada correção tem teste **e contrapartida**; o teste do guarda força a condição em vez de fingir um PDF que a produza, e diz isso na docstring |
| 9 | Migration safety | 2 | [—] | Não se aplica: nenhuma mudança de schema |

Média ponderada: 98/100 → **9.8**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

### S-1 · Dois reenvios simultâneos do mesmo documento `failed` duplicam os chunks — `backend/app/api/documents.py:138-142`

O `reset_for_retry` não é condicional. Dois POST concorrentes do mesmo PDF, com
o documento em `failed`, passam ambos pela checagem, ambos resetam e ambos
agendam ingestão. O semáforo serializa os **pipelines**, não os resets — então as
duas ingestões rodam em sequência sobre o mesmo `document_id` e cada uma insere
o conjunto inteiro de chunks. Medido por mim:

```text
apos 1o envio: failed
ids devolvidos iguais? True
resets pedidos: 2                       <- os dois POST resetaram
ingestoes que rodaram: 3                <- a que falhou + duas
```

O dublê **esconde** o efeito, e essa é a parte que mais importa: o
`FakeRepository.insert_chunks` atribui (`self.chunks[document_id] = ...`)
enquanto o Postgres acumula. Conferido contra o banco real:

```text
POSTGRES  apos duas insercoes: 6 linhas  (chunks_total diria 3)
DUBLE     apos duas insercoes: 3 linhas
```

Ou seja: nenhum teste offline pode pegar esta classe de bug enquanto o dublê
divergir do repositório real nessa operação. Na `FEAT-0002` o sintoma seria
citação duplicada e um `chunks_total` que não bate com a tabela.

**Por que sugestão e não IMPORTANTE:** exige dois POST concorrentes; o app é
declaradamente de uma ingestão por vez (NFR-8), a entrega é um avaliador com um
navegador, e a corrida análoga que já existia antes deste rework — dois uploads
concorrentes de um PDF **novo**, que colidem no `UNIQUE` e devolvem `500` — não
foi levantada na tentativa 1. Seria incoerente reprovar agora a variante e não a
original. **Se este app tivesse mais de um usuário, as duas seriam IMPORTANTES.**

**Correção sugerida, que fecha as duas de uma vez:** tornar o reset condicional e
só agendar quando ele de fato aconteceu —

```sql
UPDATE documents SET status = $2, error_message = NULL, ...
 WHERE id = $1 AND status = 'failed'
```

devolvendo o número de linhas afetadas; se for zero, outro POST já assumiu o
reprocessamento e este responde o estado atual sem agendar nada. E, no `create`,
tratar `asyncpg.UniqueViolationError` relendo por hash em vez de virar `500`.

**E alinhar o dublê ao real:** `FakeRepository.insert_chunks` deveria acumular,
como o Postgres, ou o `test_ingestion_db.py` ganhar um caso que insira duas vezes
o mesmo documento. Um dublê que mente sobre a semântica que dobra é pior que
nenhum, porque dá confiança onde não há.

### Outras

- **`document.retry` não está na tabela de §4.4** e, no caminho de reenvio,
  substitui o `document.received`. É coerente com o precedente do
  `embedding.failed` da `A.3` (a tabela não se declara exaustiva) e o evento é
  bem nomeado, mas quem contar ingestões por `document.received` passará a
  subcontar. Vale uma linha na §4.4.
- O reenvio não atualiza o `filename`: reenviar o mesmo conteúdo com outro nome
  mantém o nome antigo na tela. Cosmético, uma linha no `reset_for_retry`.
- `_elapsed_ms` em `document.ready`: a escolha declarada ("desde que a task
  começou, incluindo a espera pelo semáforo") é a certa, e agora está na
  docstring. Fechado.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 8cc9eb14 HEAD  -> OK
$ cd backend && uv run ruff check .           -> All checks passed!
$ uv run mypy app                             -> Success: no issues found in 18 source files
$ uv run lint-imports --config .importlinter  -> Contracts: 4 kept, 0 broken.
$ env -u GEMINI_API_KEY DATABASE_URL='postgresql://ninguem@127.0.0.1:1/x' uv run pytest -q
135 passed, 6 deselected in 10.12s
$ uv run pytest -m db -q                      -> 6 passed, 135 deselected
   (contra um Postgres descartável que subi de db/001_init.sql; removido ao fim)
```

**A sonda da tentativa 1, agora invertida (reenvio depois de falha, pela rota
real):**

```text
tentativa 1:  2o envio -> 202 {'status': 'failed'} | estado final: failed | nenhum lote novo
tentativa 2:  2o envio -> 202 {'status': 'pending'} | estado final: ready | error_message: None
              mesmo id? True | lotes embedados no 2o envio: 1 (reprocessou)
```

**Mutação, escrita por mim (plugin de pytest que faz a condição de status nunca
casar, reproduzindo o comportamento antigo, sem tocar no repositório):**

```text
$ pytest tests/test_ingestion_api.py::test_documento_que_falhou_e_reprocessado_no_reenvio -p mut_dedup
>       assert apos_reenvio["status"] == DocumentStatus.READY.value
E       AssertionError: assert 'failed' == 'ready'
1 failed
```

O teste falha exatamente na asserção que descreve o defeito. Não é vácuo.

**AC-29, revarredura por AST:**

```text
sem docstring: (apenas stubs de Protocol e __init__)
```

`get`, `set_status`, `set_totals` e `update_progress` da implementação concreta
têm docstring agora, e `reset_for_retry` nasceu com a dele.

**Sonda da corrida (S-1) e comparação dublê × Postgres:** saídas coladas em §5.

**Gate de conclusão da fase — `[—]` NÃO REEXECUTADO por mim.** O upload real pelo
compose exige `GEMINI_API_KEY`. O relatório traz a medição com chave inválida e
depois válida (`1o envio failed → reenvio → mesmo id, ready 10/10`), coerente com
o que reproduzi offline e com os 10 chunks que a sonda de chunking devolve para o
mesmo PDF.

## 7. Itens da fase / DoD não atendidos

Nenhum. AC-29 fechado, reenvio funcional, guarda de zero chunks implementado.
Fica em aberto, como sugestão, a corrida do reset e o alinhamento do dublê.

## 8. Divergências entre o relatório e o código real

1. **A ressalva do S-1 é verdadeira e verifiquei:** a suíte inteira passa com o
   guarda removido — ele é mesmo inalcançável hoje. Declarar isso, em vez de
   apresentar o guarda como correção de um caminho vivo, é o comportamento certo.
2. **O relatório não menciona a janela de corrida do reset** (§5, S-1). Não é
   afirmação falsa, é ausência — e é a única coisa que a §8 do EXECUCAO deixou de
   fora sobre a própria correção.
3. Todo o resto confere: `reset_for_retry` limpa chunks na mesma transação
   (verifiquei contra o Postgres: 0 linhas depois do reset), a contrapartida do
   AC-15 existe e passa, e as docstrings novas dizem o quê e por quê.
