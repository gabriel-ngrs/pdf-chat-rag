---
spec: 02-chat-rag
fase: A.7
slug_fase: hybrid-search
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: 7803d010675229801a56bbef974c3f9ace6fcd96
sha_final: 514e919d1b2148f5f8596b918d606a1c3caefd03
range: 7803d01..514e919
---

# FASE A.7 — Relatório de execução

## 1. Resumo do que foi feito

`chunks` ganhou uma coluna `tsv` gerada e um índice GIN; o repositório ganhou
`search_chunks_lexical` (ordenada por `ts_rank_cd`, filtrada por `document_id`); e
`core/retrieval.py` ganhou `reciprocal_rank_fusion`, pura e offline. A busca densa **não
foi substituída** — sem `query`, o repositório segue fazendo só a densa, e é esse default
que permitiu medir os dois modos pelo mesmo caminho de código.

**O delta no dataset é zero.** As seis métricas e as tabelas por pergunta saem idênticas.
Em consulta por **termo literal** — que o dataset não contém — a fusão conserta o que a
densa perde: `contato@exemplo.com.br` não aparecia no top-3 denso e passa à 2ª posição.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `backend/tests/test_rrf.py` | 9 testes puros da fusão + 5 sob o marker `db` |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `db/002_conversations.sql` | Coluna `tsv` gerada em `chunks` + índice GIN |
| `backend/app/adapters/repository.py` | `search_chunks_lexical`; `search_chunks` funde quando recebe `query` |
| `backend/app/core/retrieval.py` | `reciprocal_rank_fusion` e a constante `RRF_K` |
| `backend/eval/README.md` | Antes e depois, com o delta e a limitação do dataset |
| `backend/app/chat.py` | Passa a `query` ao retrieval e deixa de reordenar (ver §4) |
| `backend/eval/run_eval.py` | Flag `--hybrid`, para medir os dois modos (ver §4) |
| `backend/tests/fakes.py` | Assinatura do dublê acompanhando o protocolo (ver §4) |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `RetrievedChunk`, `vector_literal`, `similarity_from_distance` e
`take_top_k` foram consumidos, não duplicados; o protocolo `ConversationRepository` foi
estendido. Nenhuma dependência nova — a busca lexical é do próprio Postgres, e a fusão são
vinte linhas puras. Nenhum framework de RAG entrou (`make arch` mantém os quatro contratos).

### Decisões

- **A fusão vive em `core/` e não toca banco** (contrato `pure-core` KEPT). Ela recebe
  duas listas ordenadas e devolve uma; quem lê o banco é o adapter.
- **`k = 60`**, o valor do artigo original. O porquê está na docstring e tem teste: com
  `k` grande as posições ficam achatadas e **aparecer nas duas listas** vale mais que
  liderar uma; com `k = 0` a liderança volta a dominar. As duas pontas são asseridas.
- **Cada chunk sai com o score denso**, não com o valor da fusão. O limiar é medido em
  cosseno e foi calibrado contra uma distribuição de cossenos (`A.5`) — trocar o campo
  por um número de outra escala apagaria a calibração. A fusão decide **a ordem**; o
  limiar continua decidindo **se responde**. É o passo 4 do plano da fase, e tem teste.
- **A busca lexical devolve a distância de cosseno junto.** Sem isso, um chunk que só a
  via lexical encontrou chegaria à fusão sem score, e o limiar não teria o que comparar.
  Custa uma operação por linha já lida.
- **`plainto_tsquery` e não `to_tsquery`**: a pergunta vem digitada por gente, e o
  `to_tsquery` exige sintaxe de operadores — um `?` viraria erro de sintaxe do Postgres.
  Tem teste (`test_pergunta_com_pontuacao_nao_vira_erro_de_sintaxe`).
- **`ts_rank_cd` e não `ts_rank`**: o `_cd` considera a proximidade entre os termos.

### DESVIOS

Três arquivos fora da lista declarada da fase. Nenhum é opcional:

1. **`backend/app/chat.py`** — uma linha para passar a `query` ao retrieval, e a remoção
   do `take_top_k` que vinha depois. Sem a primeira, a fusão existiria e o produto não a
   usaria; sem a segunda, o chamador reordenaria por score denso a lista que a fusão
   acabou de ordenar, apagando o efeito. O corte de top-k passou para o repositório, que
   é quem tem as duas listas — `take_top_k` continua sendo código de produção, chamado lá.
2. **`backend/eval/run_eval.py`** — a flag `--hybrid`. O gate da fase é o delta antes e
   depois; sem ela não há como medir. Ela também é o que torna a medição honesta: o
   mesmo caminho de código nos dois modos, com uma variável só.
3. **`backend/tests/fakes.py`** — a assinatura do dublê acompanha o protocolo, senão
   toda a suíte de chat quebraria com `TypeError`.

## 5. Comandos rodados + saídas reais

```text
$ cd backend && uv run ruff check .            -> All checks passed!
$ uv run mypy app                              -> Success: no issues found in 23 source files
$ uv run mypy eval                              -> Success: no issues found in 1 source file
$ uv run lint-imports --config .importlinter   -> Contracts: 4 kept, 0 broken.

$ make check
Required test coverage of 90% reached. Total coverage: 99.58%
272 passed, 24 deselected in 12.30s
Test Files  10 passed (10) | Tests  84 passed (84)

$ uv run pytest -m db -q                       -> 24 passed, 272 deselected in 2.41s
$ uv run bandit -q -r app                      -> exit 0
```

**Schema aplicado, conferido em banco vazio recriado** (`docker compose down -v` + `up`):

```text
 tsv | tsvector | generated always as (to_tsvector('portuguese'::regconfig, content)) stored
Indexes:
    "chunks_embedding_idx" hnsw (embedding vector_cosine_ops)
    "chunks_tsv_idx" gin (tsv)
```

### A medição: antes e depois

Baseline **remedida** sobre o corpus novo, e não copiada da `A.5` — o `make down` apagou o
documento daquela rodada, e comparar contra ele misturaria a fusão com uma reingestão
diferente. Documento `89774e1c-009d-47c5-80e4-ba6c7324f3d3`, 10 chunks, 3 páginas.

| métrica | densa | híbrida | delta |
|---|---|---|---|
| `recall@1` | 0.917 | 0.917 | **0.000** |
| `recall@3` | 1.000 | 1.000 | **0.000** |
| `MRR` | 0.958 | 0.958 | **0.000** |
| recusa correta | 1.000 | 1.000 | 0.000 |
| falsa recusa | 0.000 | 0.000 | 0.000 |

`diff` das tabelas por pergunta: **vazio**. Nenhuma posição mudou em nenhum dos 16 itens.

**O caso que o dataset não exercita**, medido no mesmo documento com a API real:

| consulta | posição do trecho com o termo — densa | híbrida |
|---|---|---|
| `contato@exemplo.com.br` | **ausente do top-3** | **2ª** |
| `sigla do documento` | 2ª | **1ª** |
| `Empresa-X` | 1ª | 1ª |

### Prova de que os testes mordem

O teste que dá sentido à fase falha quando a fusão é desligada — desligando só as duas
linhas que fundem, no repositório:

```text
# sem a fusão
FAILED tests/test_rrf.py::test_termo_exato_raro_entra_no_resultado_pela_via_lexical
1 failed, 4 passed, 9 deselected in 0.39s

# com a fusão
5 passed, 9 deselected in 0.34s
```

Os nove testes puros continuam passando nos dois estados, e é correto que continuem: eles
exercitam a função de fusão, que existe nos dois casos. Quem prova a **fiação** é o teste
`db`.

## 6. Critérios de aceite da fase (com evidência)

- [x] **Coluna `tsv` gerada e índice GIN** — `\d chunks` colado acima, em banco recriado.
- [x] **`search_chunks_lexical` com `ts_rank_cd`, parametrizada e filtrada por `document_id`** —
  `test_busca_lexical_isola_por_documento` prova o isolamento com um documento vizinho que
  contém o mesmo e-mail.
- [x] **`reciprocal_rank_fusion(dense, lexical, k=60)` pura em `core/`** — 9 testes
  offline, incluindo a ordenação completa conferida contra a soma feita à mão e a pureza
  (as listas de entrada não são alteradas).
- [x] **O limiar continua sobre o score denso** — `test_score_que_sai_e_o_denso_e_nao_o_da_fusao`.
- [x] **Chunk com termo exato raro recuperado pela via lexical** —
  `test_termo_exato_raro_entra_no_resultado_pela_via_lexical`, com vetores construídos à
  mão para que "a densa não acha" seja desenho e não sorte; e a medição real na tabela acima.
- [x] **Delta medido e registrado, com `make eval` antes e depois** — §5 e a seção nova do
  `backend/eval/README.md`.
- [x] **`make check` zero** — 272 offline, 24 `db`, cobertura 99,58%.
- [x] **A densa não foi substituída** — sem `query`, `search_chunks` devolve exatamente o
  que devolvia; `test_lista_lexical_vazia_devolve_a_densa_intacta` e
  `test_pergunta_sem_termo_no_documento_nao_quebra_a_busca` travam isso.

## 7. Definition of Done da fase

- [x] Testes verdes; comandos de validação limpos
- [x] Escopo travado: fusão em `core/` sem tocar banco; densa não substituída; fase
      executada com `A.1`–`A.6` e `B.1`–`B.4` concluídas; `B.5` não iniciada
- [x] Nenhum segredo/PII; commit em pt-BR (Conventional Commits)
- [x] `make down` combinado com a sessão par antes de derrubar o volume

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

- **O delta zero é o ponto que mais merece olhar externo.** A spec manda reverter se o
  delta for negativo; ele é zero, e o mecanismo tem ganho medido fora do dataset. Mantive
  a fusão, mas reverter é defensável — o custo dela é uma segunda consulta ao banco por
  turno. A decisão de manter está registrada aqui e no `eval/README.md`, com os dois
  números à vista.
- **A limitação que a fase revelou no dataset da `A.5`**: nenhuma das 16 perguntas é uma
  consulta por termo literal, e por isso as métricas não conseguem ver o problema que
  esta fase resolve. Acrescentar duas perguntas literais mudaria isso — e mudaria o
  `recall@1` da baseline para baixo, tornando o delta visível. **Não fiz**, de propósito:
  mexer no dataset no meio de uma medição de antes e depois é o que a `A.5` proíbe.
- **A medição do termo literal foi feita por script descartável**, fora do repositório, e
  não é reprodutível por um alvo do Makefile. Se o avaliador quiser reproduzi-la, o
  caminho é o `document_id` acima e três chamadas a `search_chunks` com e sem `query`.
- **A ordem final passou a ser a da fusão**, e não a do score denso. Nas citações isso
  significa que os chips não vêm mais necessariamente em ordem decrescente de score. É
  consequência direta do passo 3 da fase, mas é uma mudança visível na interface que
  ninguém pediu explicitamente.
