---
spec: 02-chat-rag
fase: A.3
slug_fase: retrieval
status: rework
tentativa: 2
reprovacoes: 1
sha_inicial: 604391b091686eb4ad60533f307b2006f0313b60
sha_final: e2b78250d82d3317abefa9359ac2a46d694a6105
range: 604391b..e2b7825
---

# FASE A.3 — Relatório de execução

## 1. Resumo do que foi feito

`search_chunks` no repositório, com `ORDER BY embedding <=> $2::vector` — o operador que
o índice HNSW de cosseno atende — e o filtro por `document_id` dentro da própria query.
`core/retrieval.py` concentra as regras puras: conversão de distância em similaridade em
`[0,1]`, limiar, top-k e recorte do trecho da citação em fronteira de palavra. 17 testes
offline e 6 contra o Postgres real; o plano de execução foi conferido com `EXPLAIN`.

**Nesta segunda tentativa**, o achado I-1 da avaliação foi corrigido: a busca passou a
ligar a varredura iterativa do HNSW, sem a qual ela devolvia **menos linhas do que o
`LIMIT` pedia** no regime em que o índice é de fato usado — e a falta virava recusa falsa
silenciosa. Ver §8.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `backend/app/core/retrieval.py` | `similarity_from_distance`, `filter_by_threshold`, `take_top_k`, `has_grounding`, `build_snippet` |
| `backend/tests/test_retrieval.py` | 17 testes offline + 6 sob o marker `db` |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/app/adapters/repository.py` | +`_SEARCH_CHUNKS_SQL`, `_ITERATIVE_SCAN_SQL` e `search_chunks` (protocolo + implementação) |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `RetrievedChunk` veio de `core/models.py` (`A.1`); o `vector_literal`
usado para passar o embedding como parâmetro já existia da `FEAT-0001`; o `ConversationRepository`
foi estendido, não duplicado. Nenhuma dependência nova.

**Decisões:**

- **`search_chunks` entrou no protocolo `ConversationRepository`**, e não num terceiro
  protocolo. A busca é um passo do turno de chat como os outros: quem persiste a
  pergunta é quem recupera os trechos e quem grava a resposta. Um protocolo separado
  produziria duas dependências que sempre viajam juntas e sempre apontam para o mesmo
  objeto. Documentado na docstring do protocolo.
- **A conversão distância → similaridade acontece no adapter, chamando `core`.** O
  resto do pipeline recebe score em `[0,1]` e nunca precisa saber que existiu uma
  distância. O grampo em `[0,1]` não é zelo: o float volta do banco com resíduo
  (`-2e-8`, `1.0000000004`), e score negativo vazando para a citação faria a interface
  exibir relevância impossível.
- **`take_top_k` reordena por score** em vez de confiar na ordem do `ORDER BY`: ele
  também recebe listas já filtradas (e, na `A.7`, fundidas), e depender da ordem de
  chegada tornaria o resultado sensível a quem chamou antes.
- **As reticências entram dentro do limite** de 240 caracteres, para que o texto
  exibido nunca passe do que a spec promete.
- **A busca roda dentro de uma transação, só para caber o `SET LOCAL`** da varredura
  iterativa. `SET LOCAL` e não `SET`: a conexão volta ao pool sem levar consigo uma
  opção de planejamento que mudaria, em silêncio, o comportamento da próxima consulta a
  pegá-la. `relaxed_order` e não `strict_order` porque `take_top_k` já reordena por
  score — pagar pela ordenação estrita no banco seria pagar duas vezes pela mesma
  garantia.

Nenhum desvio da spec nesta fase.

## 5. Comandos rodados + saídas reais

```text
# lint
$ cd backend && uv run ruff check app/core/retrieval.py tests/test_retrieval.py app/adapters/repository.py
All checks passed!

# type-check
$ uv run mypy app
Success: no issues found in 21 source files

# testes offline da fase
$ uv run pytest tests/test_retrieval.py -p no:cacheprovider --no-cov -q
.................
17 passed, 6 deselected in 0.03s

# testes contra o Postgres do compose
$ uv run pytest tests/test_retrieval.py -m db -p no:cacheprovider --no-cov -q
......
6 passed, 17 deselected in 1.34s

# gate agregado do projeto (árvore inteira, já com Track B integrado)
$ make check
All checks passed!
Success: no issues found in 23 source files
Contracts: 4 kept, 0 broken.
Required test coverage of 90% reached. Total coverage: 99.55%
260 passed, 19 deselected in 11.49s
Test Files  10 passed (10) | Tests  75 passed (75)

# grep de segredo/PII no diff (esperado: 0)
$ git diff 604391b..7fe47de | grep -ciE "AIza|api[_-]?key *=|postgresql://.*:.*@"
0
```

**`EXPLAIN ANALYZE` da query real** (documento com 2.000 chunks, `ANALYZE chunks` rodado
antes; o vetor da cláusula foi elidido aqui por tamanho):

```text
Limit  (cost=37.33..47.77 rows=5 width=67) (actual time=0.778..0.796 rows=5 loops=1)
  ->  Index Scan using chunks_embedding_idx on chunks
        (cost=37.33..4213.00 rows=2000 width=67) (actual time=0.776..0.794 rows=5 loops=1)
        Order By: (embedding <=> '[...768 valores...]'::vector)
        Filter: (document_id = '6129e70e-...'::uuid)
Planning Time: 0.159 ms
Execution Time: 0.882 ms
```

O `Index Scan using chunks_embedding_idx` com `Order By: (embedding <=> ...)` é a prova
de que o operador escolhido casa com o opclass `vector_cosine_ops` do índice HNSW.

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-6 (isolamento por documento)** — `test_busca_nao_atravessa_a_fronteira_do_documento`:
  dois documentos ingeridos na mesma sessão; a busca no documento A com o **vetor de um
  chunk do documento B** devolve só conteúdo de A.
- [x] **AC-7 (top-k ordenado, score em `[0,1]`)** — `test_busca_volta_ordenada_e_respeita_o_limite`
  contra o banco real, mais `test_top_k_devolve_os_melhores_em_ordem_decrescente` offline.
- [x] **AC-8 (nada acima do limiar → lista vazia e sem fundamento)** —
  `test_tudo_abaixo_do_limiar_deixa_a_lista_vazia_e_sem_fundamento`.
- [x] **AC-26 (`RETRIEVAL_TOP_K` do ambiente)** — `test_top_k_configurado_no_ambiente_e_respeitado`:
  `monkeypatch.setenv("RETRIEVAL_TOP_K", "2")` e o corte passa a 2, sem mudança de código.
- [x] **AC-10 (snippet nunca corta palavra)** — `test_snippet_nunca_corta_palavra_ao_meio`,
  `test_snippet_longo_cabe_no_limite_e_termina_em_reticencias`, e o caso de palavra única
  maior que o limite.
- [x] **Busca real devolve o chunk certo** — `test_busca_devolve_o_chunk_certo_com_score_maximo`:
  o vetor da própria frase recupera aquela frase, com score `1.0` e a página correta.
- [x] **Gate da fase, na leitura estrita: a busca devolve a quantidade pedida** —
  `test_busca_entrega_o_limite_pedido_mesmo_com_o_indice_em_uso`, no regime em que o
  índice é usado. Ver §8 para a prova de que ele falha sem a correção.
- [x] **A opção de planejamento não vaza da transação** —
  `test_a_varredura_iterativa_nao_vaza_para_as_outras_consultas`.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (17 offline + 4 `db`)
- [x] Comandos de validação limpos; `make check` zero
- [x] Escopo travado respeitado: filtro por `document_id` na query (não opcional), `core/retrieval.py` sem banco, nenhum SQL concatenado, operador `<=>`
- [x] Nenhum segredo/PII
- [x] Commit em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

**Achado I-1 da avaliação — corrigido.** A avaliação mostrou que, num `Index Scan` sobre
HNSW, o pgvector devolve os vizinhos **globais** mais próximos (até `ef_search`) e só
então o `WHERE document_id` descarta o que veio de outro documento; com a varredura
iterativa desligada — o default do pgvector 0.8 — o descartado **não é reposto**. A busca
devolvia menos linhas do que o `LIMIT` pedia, `has_grounding` dava falso, e o turno
recusava uma pergunta que o documento responde. Sem erro, sem log anômalo.

**A correção** foi a primeira das três opções sugeridas: `SET LOCAL hnsw.iterative_scan =
relaxed_order` na transação da busca (`repository.py`), com o porquê registrado numa
constante nomeada. `relaxed_order` porque `take_top_k` já reordena por score.

**O teste que faltava** foi escrito e é o ponto que dá valor à correção. Ele reproduz o
regime com dados pequenos: `ALTER ROLE talkdoc SET enable_seqscan = off` e
`hnsw.ef_search = 2`, um pool **criado depois disso** (configuração de papel só vale para
conexão nova — sem essa ordem o teste passaria sem exercitar nada), um documento alvo com
20 chunks e um documento vizinho com 200.

Prova de que o teste morde — a mesma suíte, com e sem a linha da correção:

```text
# sem `SET LOCAL hnsw.iterative_scan = relaxed_order`
$ uv run pytest tests/test_retrieval.py -m db -p no:cacheprovider --no-cov -q
>       assert len(recuperados) == 5
E       assert 0 == 5
E        +  where 0 = len([])
FAILED tests/test_retrieval.py::test_busca_entrega_o_limite_pedido_mesmo_com_o_indice_em_uso
1 failed, 5 passed, 17 deselected in 0.97s

# com a correção
$ uv run pytest tests/test_retrieval.py -m db -p no:cacheprovider --no-cov -q
......
6 passed, 17 deselected in 0.72s
```

Reprodução independente do efeito, contra o banco do projeto, antes de escrever o teste:

```text
seqscan: off | ef_search: 2
   Limit  (cost=10.43..1027.09 rows=5 width=12)
     ->  Index Scan using chunks_embedding_idx on chunks  (cost=10.43..4077.05 rows=20 width=12)
           Order By: (embedding <=> '[...]'::vector)
           Filter: (document_id = 'd0e3979c-...'::uuid)
SEM iterative_scan -> linhas: 0
COM iterative_scan -> linhas: 5
```

Nada mais foi tocado: as regras puras de `core/retrieval.py` não mudaram uma linha.

## 9. Itens em aberto / dúvidas para o avaliador

- **O `EXPLAIN` foi feito com um documento sintético de 2.000 chunks**, criado e apagado
  por um script descartável fora do repositório. Com os ~10 chunks do
  `documento-de-exemplo.pdf` o planejador escolheria varredura sequencial — e estaria certo:
  numa tabela desse tamanho ela é mais barata. O que precisava ser provado é que o
  operador da query casa com o opclass do índice, e é isso que o plano acima mostra.
- **O teste novo força o regime em vez de esperá-lo.** Ele mexe em duas opções de
  planejamento do papel `talkdoc` e as devolve num `finally`. É a única forma que
  encontrei de exercitar o caminho com dados pequenos; a alternativa — inserir milhares
  de chunks para o planejador escolher o índice sozinho — seria mais lenta e menos
  determinística. Se o avaliador preferir a segunda forma, o teste é reescrevível.
- **Continua não havendo teste automatizado da *escolha* do planejador**, e
  deliberadamente: ela muda com o volume de dados e um teste assim seria frágil por
  natureza. O que passou a ter teste é a **consequência** que importa — a quantidade de
  linhas devolvida quando o índice é usado.
- **`similarity_from_distance` arredonda a 3 casas.** É a precisão que alguém lê num
  chip de citação; se o avaliador preferir o score cru no payload e o arredondamento só
  na exibição, é uma linha.
