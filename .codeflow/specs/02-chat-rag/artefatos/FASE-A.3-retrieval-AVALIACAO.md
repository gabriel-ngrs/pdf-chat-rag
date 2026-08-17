---
spec: 02-chat-rag
fase: A.3
slug_fase: retrieval
tentativa: 2
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: 604391b091686eb4ad60533f307b2006f0313b60..e2b78250d82d3317abefa9359ac2a46d694a6105
---

# FASE A.3 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. O achado I-1 da tentativa 1 está fechado, e
eu não me contentei em ler a correção: **reproduzi o defeito e a cura contra o
banco do projeto**, com dados sintéticos criados e apagados por mim (§6). No
mesmo cenário — documento alvo de 20 chunks, vizinho de 200, `Index Scan`
forçado, `ef_search = 2` — a query pediu 5 e recebeu **0** sem a linha da
correção, e **5, todas do documento certo**, com ela.

O que mais pesa a favor da tentativa: o executor **provou o teste falhando**
antes de corrigir, colando o `assert 0 == 5`. Um teste de regressão que ninguém
viu vermelho é uma afirmação, não uma garantia.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | AC-6/AC-7/AC-8/AC-10/AC-26 seguem provados; o gate "busca real devolve chunks do documento certo" agora vale **também** no regime de índice, que é onde não valia (§6) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | A correção ficou no adapter, onde o SQL mora; `core/retrieval.py` não mudou uma linha — as regras puras seguem puras, `pure-core` KEPT |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `_ITERATIVE_SCAN_SQL` (`repository.py:143`) é literal constante, sem entrada externa (GUC não aceita placeholder, e o comentário diz isso); `SET LOCAL` não vaza para o pool — testado (`test_retrieval.py:344`) e reconferido por mim |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Nada duplicado; `take_top_k` continua sendo quem ordena, e é por isso que `relaxed_order` basta |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `relaxed_order` em vez de `strict_order` é a escolha certa e está justificada: conferi que `filter_by_threshold`, `take_top_k` e `_top_score` são todos indiferentes à ordem de chegada |
| 6 | Local e nomes dos arquivos | 2 | 5 | Só `repository.py` e `test_retrieval.py`, ambos da fase |
| 7 | Qualidade de código | 2 | 4 | Comentário de 15 linhas explicando o porquê, no ponto certo; desconta: a fixture usa `ALTER ROLE`, que muda estado **global** do banco (§5) |
| 8 | Testes e cobertura | 2 | 5 | Dois testes novos sob `db` — o de regressão e o de não-vazamento —, com o de regressão **demonstrado falhando** sem a correção; 19 testes `db` verdes na minha execução |

Score = (5·3 + 5·3 + 5·3 + 5·3 + 5·2 + 5·2 + 4·2 + 5·2) / 20 × 2 = **9.8**

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum. O I-1 da tentativa 1 está **fechado e verificado independentemente**.

## 5. Sugestões

- **`backend/tests/test_retrieval.py:301-310` — a fixture muda estado global do
  banco.** `ALTER ROLE talkdoc SET enable_seqscan = off` persiste no papel, não
  na sessão: se o processo de teste morrer entre o `ALTER` e o `RESET` do
  `finally` (SIGKILL, falta de energia, timeout do CI), o papel fica com
  `seqscan` desligado **para sempre**, e toda consulta do projeto passa a rodar
  num plano que ninguém escolheu. O `try/finally` cobre o caso normal e o
  cenário é remoto — mas existe uma alternativa sem estado global: criar o pool
  do teste com `asyncpg.create_pool(..., server_settings={"enable_seqscan":
  "off", "hnsw.ef_search": "2"})`, que aplica as opções por conexão. O teste
  usa um pool próprio de qualquer forma, então trocar o `Database` do projeto
  por um `create_pool` direto ali não custa nada.
- **Custo novo por busca: uma conexão adquirida e uma transação aberta**
  (`repository.py:521`). Antes era `pool.fetch` direto. É desprezível em
  absoluto, e o `SET LOCAL` exige a transação — mas fica registrado que a busca
  passou a ser a única leitura do projeto que abre transação, o que alguém pode
  estranhar depois sem o comentário que hoje está lá.
- **Mantida da tentativa 1, ainda válida:** `similarity_from_distance`
  arredondando a 3 casas. O executor optou por não mexer, citando a minha
  própria conclusão de que não muda decisão nenhuma com 0,10 de folga de cada
  lado. Concordo — registro só para não ser redescoberto.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh \
       .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ §5 estruturalmente válida
EXIT=0

$ git merge-base --is-ancestor e2b7825 HEAD && echo OK
OK

$ make check
Contracts: 4 kept, 0 broken.
app/core/retrieval.py         21      0      4      0   100%
Required test coverage of 90% reached. Total coverage: 99.55%
262 passed, 19 deselected in 11.28s
Test Files  10 passed (10) | Tests  84 passed (84)
[exited with code 0]

$ make security
bandit -q -r app             → (sem saída)
pip-audit                    → No known vulnerabilities found
npm audit --audit-level=high → found 0 vulnerabilities
SEC=0

$ cd backend && uv run pytest -m db -p no:cacheprovider --no-cov -q
19 passed, 262 deselected in 1.71s
```

**Reprodução independente do defeito e da cura.** Criei dois documentos
sintéticos sob um `session_id` próprio (`AVALIADOR-…`), rodei a query exata do
adapter com e sem a linha da correção, e apaguei tudo no fim:

```text
documento alvo: 20 chunks | vizinho: 200 chunks | LIMIT pedido: 5
  SEM  SET LOCAL hnsw.iterative_scan -> 0 linhas
  COM  SET LOCAL hnsw.iterative_scan -> 5 linhas
  todas do documento alvo? True
  plano: ->  Index Scan using chunks_embedding_idx on chunks  (cost=492.30..508.80 rows=1 width=471)
limpeza: chunks restantes no banco = 10
```

Zero linhas. O turno recusaria uma pergunta que o documento responde — que é
exatamente o que o achado descrevia, e agora está medido nos dois estados.

**Confirmação de que a opção não vaza da transação:**

```text
$ SHOW hnsw.iterative_scan   (depois de uma busca, na mesma conexão)
off
```

**Estado do banco ao fim da avaliação** (nada meu ficou para trás, GUCs de papel
restaurados):

```text
documentos: 2 | chunks: 18        (os dois do gate do executor, nenhum meu)
enable_seqscan: on | hnsw.ef_search: 40 | hnsw.iterative_scan: off
```

## 7. Itens da fase / DoD não atendidos

Nenhum. O critério de conclusão da fase — "busca real devolve chunks do
documento certo **e** `EXPLAIN` mostra uso do índice" — agora vale nas duas
metades **ao mesmo tempo**, que era precisamente a conjunção que a tentativa 1
não exercitava.

## 8. Divergências entre o relatório e o código real

Nenhuma. O §8 do `EXECUCAO` descreve a correção, o teste e a prova de que o
teste morde; conferi os três contra o código, contra a suíte e contra o banco. A
saída que o relatório cola (`assert 0 == 5`) é coerente com o que a minha
reprodução independente mediu (0 linhas sem a correção).

**Nota de perímetro, fora da responsabilidade desta fase:** o `HEAD` da branch
(`e76fbed`) é posterior ao `range` avaliado e alterou `backend/app/chat.py` e
`backend/tests/test_chat_api.py` — arquivos do Track A — dentro de um rework do
Track B. Não toca nada desta fase; está registrado aqui e no fecho conjunto
porque é a mesma classe de problema que o I-1 da `A.6` fechou.
