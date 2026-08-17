---
spec: 02-chat-rag
fase: A.3
slug_fase: retrieval
tentativa: 1
veredito: RESSALVAS
score: 9.3
threshold: 8.5
range_avaliado: 604391b091686eb4ad60533f307b2006f0313b60..7fe47de9ac92e62523d38eab7366615b7d70d0bb
---

# FASE A.3 — Avaliação independente

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 9.3 / threshold 8.5

Zero BLOQUEANTES. **Um IMPORTANTE**, e é o achado mais consequente desta
avaliação: no regime em que o índice HNSW é de fato usado, a query de
`search_chunks` pode devolver **menos chunks do que o `LIMIT` pede** — no limite,
zero —, porque o filtro por `document_id` é aplicado **depois** do índice. Isso
vira falsa recusa silenciosa. Reproduzi o efeito no banco do projeto (§6).

O resto da fase é sólido: confirmei de forma independente que o operador `<=>`
casa com o opclass `vector_cosine_ops` do índice, e o isolamento por documento,
o top-k e o recorte do snippet estão provados por teste.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 4 | AC-6/AC-7/AC-8/AC-10/AC-26 provados (`tests/test_retrieval.py:52-157,214-269`); o operador `<=>` é o do índice, confirmado por mim com `EXPLAIN` (§6); desconta: o gate "busca real devolve chunks do documento certo" não vale **na quantidade pedida** quando o índice é usado (§4) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `core/retrieval.py` importa só `core.models`; a conversão distância→score acontece no adapter chamando `core` (`repository.py:508`), e o resto do pipeline nunca vê distância; `pure-core` KEPT |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `_SEARCH_CHUNKS_SQL` é 100% placeholder (`repository.py:118-124`); o `document_id` entra no `WHERE` da própria query, não como filtro em Python; `tests/test_chat_security.py:441` assere que não há interpolação |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `RetrievedChunk` e `vector_literal` reusados; `search_chunks` entrou no protocolo existente em vez de criar um terceiro, com a razão documentada (`repository.py:194-197`) |
| 5 | Padrões de domínio/aplicação | 2 | 4 | Limiar `>=`, grampo em `[0,1]` contra resíduo de float e `take_top_k` reordenando por conta própria são acertos; desconta: o par "HNSW + filtro posterior" é a forma reconhecidamente frágil de busca vetorial filtrada (§4) |
| 6 | Local e nomes dos arquivos | 2 | 5 | Os três caminhos batem com a lista da fase |
| 7 | Qualidade de código | 2 | 5 | Cinco funções puras, todas curtas e com docstring de "por quê"; `build_snippet` põe as reticências **dentro** do limite, o que o teste cobra |
| 8 | Testes e cobertura | 2 | 4 | 17 offline + 4 sob `db`, `core/retrieval.py` em 100%; desconta: nenhum teste exercita a busca com **mais de um documento no índice** em escala em que o plano use o índice — que é exatamente onde o achado de §4 mora |

Score = (4·3 + 5·3 + 5·3 + 5·3 + 4·2 + 5·2 + 5·2 + 4·2) / 20 × 2 = **9.3**

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

### I-1 — `backend/app/adapters/repository.py:118-124`: o filtro por `document_id` é aplicado depois do índice HNSW, e a busca pode devolver menos chunks do que pediu

```sql
SELECT chunk_index, page_number, content, embedding <=> $2::vector AS distance
  FROM chunks
 WHERE document_id = $1
 ORDER BY embedding <=> $2::vector
 LIMIT $3
```

Num `Index Scan` sobre HNSW, o pgvector devolve os vizinhos **globais** mais
próximos (até `ef_search`, default 40) e só então o `Filter: (document_id = ...)`
descarta o que veio de outro documento. Com `hnsw.iterative_scan` desligado — que
é o **default** do pgvector 0.8 e é como o `db/001_init.sql` deixa o índice —, o
resultado não é reposto: a query simplesmente devolve menos linhas.

**Efeito no produto:** `search_chunks` devolve 2 chunks em vez de 5, ou nenhum. O
pipeline não distingue "não achei" de "o índice não me deixou ver" — `has_grounding`
dá `False` e o turno vira **recusa** (`chat.py:107-111`) numa pergunta que o
documento responde. É falsa recusa silenciosa, que ataca justamente o eixo que a
`FEAT-0002` existe para provar, e é invisível: nenhum erro, nenhum log anômalo.

**Por que não morde hoje:** com 30 chunks o planejador escolhe varredura
sequencial, que é exata. O defeito acorda quando a tabela cresce o bastante para
o índice ser escolhido — e já há três documentos no banco.

**Reproduzido por mim** (§6): forçando `Index Scan` e reduzindo `ef_search`, a
mesma query pediu 5 e recebeu **1** linha, num documento que tem 10 chunks.

**Correção sugerida** (uma das três, por ordem de custo):

1. `SET LOCAL hnsw.iterative_scan = relaxed_order` na conexão antes da busca
   (pgvector ≥ 0.8, que é o da imagem) — o índice passa a repor candidatos até
   completar o `LIMIT`;
2. subir `hnsw.ef_search` para um múltiplo do top-k;
3. se nenhuma entrar, **registrar em "limitações conhecidas" do README** (`B.5`)
   com estas palavras: a busca é exata enquanto o corpus for pequeno.

Qualquer que seja a escolha, acrescentar o teste que falta: com dois documentos
e o índice forçado, `search_chunks(A, ...)` devolve `min(limit, chunks de A)`.

## 5. Sugestões

- **`repository.py:508` — `similarity_from_distance` arredonda a 3 casas antes de
  o score circular.** O próprio relatório levanta a alternativa (score cru no
  payload, arredondamento só na exibição). Como o limiar medido na `A.5` tem
  ~0,10 de folga para cada lado, três casas não mudam nenhuma decisão. Fica como
  está; anotado para não ser redescoberto.
- **`core/retrieval.py:62` — `take_top_k` reordena o que o `ORDER BY` já ordenou.**
  Custo desprezível e a razão está documentada (a `A.7` passaria listas fundidas).
  Concordo com a decisão.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 7fe47de HEAD && echo OK
OK

$ make check
Contracts: 4 kept, 0 broken.
app/core/retrieval.py         21      0      4      0   100%
Required test coverage of 90% reached. Total coverage: 99.55%
248 passed, 17 deselected in 11.67s
Test Files  10 passed (10) | Tests  75 passed (75)
[exited with code 0]

$ cd backend && uv run pytest -m db -p no:cacheprovider --no-cov -q
17 passed, 248 deselected in 3.42s
```

**Confirmação independente de que o `<=>` casa com o opclass do índice** — com
`enable_seqscan = off` para tirar o tamanho da tabela da conta:

```text
Limit  (cost=4033.42..4047.78 rows=1 width=67)
  ->  Index Scan using chunks_embedding_idx on chunks  (cost=4033.42..4047.78 rows=1 width=67)
        Order By: (embedding <=> '[0.01,...]'::vector)
        Filter: (document_id = '97959135-...'::uuid)
```

**Reprodução do achado I-1** — mesma query, mesmo banco, três valores de
`ef_search`, documento com 10 chunks pedindo 5:

```text
chunks por documento: [('d136750b', 10), ('97959135', 10), ('64e6f8bf', 10)]

ef_search= 40 -> 5 linhas (pedidas 5) para o documento d136750b
ef_search=  4 -> 1 linhas (pedidas 5) para o documento d136750b
ef_search=  1 -> 1 linhas (pedidas 5) para o documento d136750b
```

O que `ef_search` baixo simula aqui é o que o **volume** produz em produção: o
vizinhado global deixa de ser dominado pelo documento da conversa.

## 7. Itens da fase / DoD não atendidos

- **Critério de conclusão da fase:** "busca real devolve chunks do documento
  certo **e** `EXPLAIN` mostra uso do índice". As duas metades foram provadas
  isoladamente — a primeira em varredura sequencial, a segunda com um documento
  sintético de 2.000 chunks (todos do mesmo documento, portanto sem filtro
  efetivo). **A conjunção nunca foi exercitada**, e é nela que o I-1 mora.
- Demais `Passos` (1–5) e `Testes` da fase: atendidos com evidência.

## 8. Divergências entre o relatório e o código real

- **Nenhuma divergência factual.** O `EXPLAIN` colado no relatório é reprodutível
  e o operador é mesmo o do índice — reconfirmei acima.
- **Uma leitura otimista, porém:** o relatório apresenta o plano com 2.000 chunks
  como prova de que "a busca real devolve chunks do documento certo" **e** usa o
  índice. Naquele cenário todos os 2.000 chunks eram do mesmo documento, então o
  `Filter` não descartou nada — o teste não podia expor o I-1. A afirmação do
  relatório é verdadeira; a garantia que o leitor tira dela é maior do que a
  evidência sustenta.
