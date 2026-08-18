---
spec: 02-chat-rag
fase: A.7
slug_fase: hybrid-search
tentativa: 1
veredito: APROVADO
score: 9.6
threshold: 8.5
range_avaliado: 7803d010675229801a56bbef974c3f9ace6fcd96..514e919d1b2148f5f8596b918d606a1c3caefd03
---

# FASE A.7 — Avaliação independente

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.6 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. **A fase está concluída, e com ela o Track A
inteiro.**

O que sustenta o veredito, verificado por mim e não lido no relatório: o schema
está aplicado como pedido (§6), a fusão vive em `core/` e é pura, a busca densa
**não** foi substituída, o limiar continua sobre o score de cosseno, e o teste
morde — neutralizando a fusão por injeção, o teste do termo exato falha com
mensagem própria; com ela, cinco verdes.

**O delta zero é o ponto que mais merecia ceticismo, e ele sobrevive ao exame.**
Zero não é negativo, e o gate da fase pede "delta medido e registrado (mesmo se
negativo)" — foi medido, registrado, e a baseline foi **remedida** sobre a mesma
ingestão em vez de copiada da `A.5`, que era a armadilha óbvia. Manter a fusão
com delta zero é decisão discutível, e o executor a apresenta como tal em vez de
vendê-la; o ganho fora do dataset é real e tem teste offline que o prova.

**Uma correção ao relatório:** ele afirma que a ordem das citações virou "mudança
visível na UI". **Não é.** `frontend/src/components/MessageList.tsx:101-103`
reordena as citações por página e depois por `chunk_index` antes de renderizar os
chips. A ordem da fusão não chega à tela. O que muda de fato é a ordem dos
trechos **dentro do prompt** e no payload — nenhuma delas visível ao usuário
(§8).

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | Escopo travado inteiro: fusão em `core/retrieval.py:99-143` sem tocar banco (`pure-core` KEPT), densa **não** substituída (`query=None` mantém o caminho antigo), fase executada depois de A.1–A.6 e B.1–B.4; delta medido e registrado antes e depois |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `reciprocal_rank_fusion` é função pura sobre `RetrievedChunk`; o adapter é quem chama as duas buscas e funde; `Contracts: 4 kept, 0 broken` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | A pergunta do usuário entra em `plainto_tsquery` como **parâmetro** (`$2`), nunca concatenada; `plainto_tsquery` e não `to_tsquery` evita que pontuação vire erro de sintaxe — com teste (`test_pergunta_com_pontuacao_nao_vira_erro_de_sintaxe`); `document_id` no `WHERE` das duas queries, com teste de isolamento |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `take_top_k`, `similarity_from_distance` e o mesmo pool reusados; `_to_chunks` extraído em vez de duplicar a construção do `RetrievedChunk` nas duas buscas |
| 5 | Padrões de domínio/aplicação | 2 | 4 | O score que sai da fusão é o **denso**, preservando a calibração do limiar da `A.5` — decisão certa e com teste próprio. Desconta: a divergência que a fase criou com o texto do AC-7 não foi registrada em lugar nenhum (§5) |
| 6 | Local e nomes dos arquivos | 2 | 4 | Três arquivos fora da lista declarada (`chat.py`, `eval/run_eval.py`, `tests/fakes.py`), todos justificados e divulgados no §4 do relatório (§5) |
| 7 | Qualidade de código | 2 | 5 | A docstring de `reciprocal_rank_fusion` explica **por que** `k=60` com a conta na mão (0,0164 contra 0,0161) em vez de citar o artigo e seguir adiante; o SQL diz por que `ts_rank_cd` e não `ts_rank` |
| 8 | Testes e cobertura | 2 | 5 | 9 testes puros + 5 sob `db`; a mordida do teste `db` provada por mim (§6); os vetores do teste são construídos à mão (paralelos e ortogonal) em vez de derivados de hash — sem isso "a densa não acha" seria sorte, e é a decisão de teste mais fina da fase |
| 9 | Migration safety | 2 | 5 | `tsv` conferida no banco recriado como `GENERATED ALWAYS ... STORED` e `chunks_tsv_idx` GIN presente (§6); `ALTER TABLE` aqui é seguro e o porquê está no próprio arquivo — roda uma vez, em banco vazio, logo depois de `001` |

Score = (5·3 + 5·3 + 5·3 + 5·3 + 4·2 + 4·2 + 5·2 + 5·2 + 5·2) / 22 × 2 = **9.6**

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **AC-7 e FR-5 ficaram desatualizados, e a fase não registrou isso.** AC-7 diz
  "no máximo 5 chunks são considerados, **ordenados por score decrescente**". A
  metade "no máximo 5" continua valendo — conferi que
  `reciprocal_rank_fusion(dense, lexical)[:limit]` corta (`repository.py:562`).
  A metade da ordenação **não**: a lista sai em ordem de fusão, com o score denso
  só como desempate. E tem de ser assim — reordenar por score denso apagaria a
  fusão, como o próprio código explica. É a mesma forma do caso FR-3 × AC-3 da
  `A.2`: o texto precisa acompanhar. **Ação para o owner:** ajustar FR-5/AC-7 via
  `/create-spec` para falar em "ordenados por relevância" em vez de "por score
  decrescente". Nada a mudar no código.
- **Três arquivos fora da lista declarada da fase**, todos no §4 do relatório:
  `chat.py` (passa a `query` e larga o `take_top_k`, que foi para o repositório —
  sem isso a fusão seria apagada na volta), `eval/run_eval.py` (a flag
  `--hybrid`, sem a qual o gate da própria fase não é medível) e `tests/fakes.py`
  (assinatura acompanhando o protocolo). Os três são matéria da própria fase e
  foram divulgados, então ficam como nota, não como achado. Registro que
  `chat.py` pertence à `A.4`, **concluída** — a mudança é posterior ao `range`
  aprovado dela e não invalida aquele veredito, mas é o quinto arquivo do Track A
  tocado por trabalho de outra fase nesta spec.
- **O dataset da `A.5` não consegue ver o problema que esta fase resolve** —
  achado do próprio executor, e é o mais útil da fase. Nenhuma das 16 perguntas é
  consulta por termo literal, e por isso o delta dá zero. **Ele fez certo em não
  mexer no dataset no meio de uma medição antes/depois.** A continuação natural,
  quando não houver medição em curso: acrescentar duas positivas de termo literal
  (`contato@yaitec.com`, `UFPB`), remedir a baseline e registrar. Aí o ganho da
  `A.7` deixa de depender de consultas ad-hoc e passa a ser reprodutível por
  `make eval`.
- **Manter a fusão com delta zero custa uma consulta a mais por turno.** É
  defensável e está documentado, e a evidência offline existe
  (`test_termo_exato_raro_entra_no_resultado_pela_via_lexical`). O que **não**
  pode acontecer é a `B.5` colar os números do eval e deixar implícito que eles
  medem a busca híbrida: eles medem os dois modos como idênticos. O README
  precisa dizer, em uma linha, que o ganho da fusão está fora do dataset e por
  quê.
- **`search_chunks_lexical` é pública mas não está no protocolo
  `ConversationRepository`.** Coerente — é detalhe da implementação Postgres, e o
  chamador só conhece `search_chunks`. Fica anotado para não ser lido depois como
  esquecimento.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh \
       .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ §5 estruturalmente válida        EXIT=0

$ git merge-base --is-ancestor 514e919 HEAD && echo OK
OK

$ make check
Contracts: 4 kept, 0 broken.
272 passed, 24 deselected
Test Files  10 passed (10) | Tests  84 passed (84)
CHECK=0

$ make security
pip-audit                    → No known vulnerabilities found
npm audit --audit-level=high → found 0 vulnerabilities
SEC=0

$ cd backend && uv run pytest -m db -p no:cacheprovider --no-cov -q
24 passed, 272 deselected in 2.00s
```

**Schema conferido no banco em execução**, não no arquivo:

```text
tsv | tsvector | gerada=ALWAYS | to_tsvector('portuguese'::regconfig, content)
IDX: chunks_embedding_idx  hnsw (embedding vector_cosine_ops)
IDX: chunks_tsv_idx        gin (tsv)
documentos: 1 | chunks: 10        (o 89774e1c-… da reingestão)
```

`GENERATED ALWAYS ... STORED` de verdade e o GIN presente — era o ponto onde um
erro passaria calado até a primeira busca lexical voltar vazia.

**Prova de que o teste morde** — neutralizei a fusão por um plugin de pytest
(`reciprocal_rank_fusion` devolvendo só a lista densa), sem tocar no
repositório:

```text
--- COM a fusão ---
5 passed, 9 deselected in 0.46s

--- SEM a fusão (neutralizada) ---
E       AssertionError: a via lexical não trouxe o trecho do termo exato
E       assert False
FAILED tests/test_rrf.py::test_termo_exato_raro_entra_no_resultado_pela_via_lexical
1 failed, 4 passed, 9 deselected in 0.49s
```

Os quatro outros testes `db` passam nos dois estados, e **é correto que passem**:
isolamento por documento, pergunta sem termo, pontuação e teto do `limit` não
dependem da fusão. Quem prova a fiação é o teste que falhou.

**Corte do top-k conferido no código, não no relatório:**

```text
repository.py:562   return reciprocal_rank_fusion(dense, lexical)[:limit]
repository.py:560   dense = take_top_k(_to_chunks(rows), limit)
```

A metade "no máximo `RETRIEVAL_TOP_K` chunks" do AC-7 continua garantida, e
`take_top_k` segue em produção — mudou de lugar, não desapareceu.

**Ordem das citações na interface, conferida no frontend:**

```text
frontend/src/components/MessageList.tsx:101
  const ordered = [...citations].sort(
    (left, right) => left.page_number - right.page_number
                     || left.chunk_index - right.chunk_index)
```

A UI reordena por página antes de renderizar os chips. A ordem da fusão **não
chega à tela** — ver §8.

**Não re-executado por mim:** `make eval` nos dois modos e as consultas ad-hoc
(`contato@yaitec.com`, `UFPB`) contra a API real. Continua sem chave utilizável
nesta sessão e a medição gasta quota do owner. O que compensa parcialmente: o
mecanismo tem prova offline no teste `db` acima, e a sequência de medição
declarada no `eval/README.md` (baseline remedida sobre a mesma ingestão) é a
correta — foi a que eu mesmo recomendei à sessão executora antes do `make down`.

## 7. Itens da fase / DoD não atendidos

Nenhum.

Os cinco `Passos` da fase estão cumpridos, incluindo o 5 ("rodar `make eval`
antes e depois e registrar o delta"), e o critério de conclusão ("delta medido e
registrado, mesmo se negativo") foi atendido com o delta **zero** registrado com
todas as letras, inclusive a explicação de por que ele é zero.

## 8. Divergências entre o relatório e o código real

**Uma, e ela é do relatório contra o próprio produto — a favor do produto.**

O §9 do `EXECUCAO` e o resumo da execução afirmam que "a ordem das citações
passou a ser a da fusão, e não mais decrescente por score — **mudança visível na
UI** que ninguém pediu". A primeira metade é verdadeira; a segunda não.
`MessageList.tsx:101-103` ordena as citações por `page_number` e depois por
`chunk_index` antes de montar os chips — comportamento que a `B.3` pediu
("ordenados por página") e que a `B.3` foi aprovada cumprindo. A ordem da fusão
morre no cliente.

O que muda de fato: a ordem dos trechos **dentro do prompt** (o modelo lê o mais
bem colocado pela fusão primeiro, que é o efeito desejado) e a ordem no payload
do evento `citations` e no `jsonb` persistido. Nenhuma das duas é visível a quem
usa.

É autocrítica excessiva, não omissão — o executor levantou contra si um risco que
não existe. Registro porque a diferença importa para o owner: **não há mudança de
interface a validar**, e o único ajuste pendente é de texto da spec (§5).

Fora isso, nenhuma divergência: as cinco decisões de §4 do relatório batem com o
código, e as três alterações de arquivo fora da lista declarada estão lá
descritas, não escondidas.
