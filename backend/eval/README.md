# Avaliações e verificações contra a API real

Aqui ficam registradas as verificações que **só a API de verdade pode responder** —
as que nenhum teste offline detecta porque o dublê, por construção, concorda com a
nossa expectativa. O registro existe para que a dúvida não volte: quem ler isto não
precisa gastar quota de novo para saber o que o provedor faz.

Nenhum teste do `make check` chama a rede. Os scripts desta pasta são rodados à mão.

---

## `scripts/check_embeddings.py` — comportamento de lote do `gemini-embedding-001`

**Pergunta:** quando três textos vão numa única requisição, o provedor devolve três
vetores ou um único vetor agregado?

**Por que importa:** o comportamento difere entre modelos do provedor. Com um vetor
agregado, o adapter gravaria vetores desalinhados dos chunks e o retrieval devolveria
trechos aleatórios — com a suíte inteira verde, porque o dublê devolve N vetores para
N textos. É a falha silenciosa mais cara desta spec.

**Como reproduzir** (a partir de `backend/`, com `GEMINI_API_KEY` no `.env` da raiz
do worktree):

```
uv run python scripts/check_embeddings.py
```

### Execução de 2026-08-17 — `google-genai 2.18.1`

```
modelo: gemini-embedding-001 | output_dimensionality: 768 | task_type: RETRIEVAL_DOCUMENT
[lista de strings] vetores devolvidos: 3 (esperado: 3)
[lista de strings]   vetor 0: dimensão=768
[lista de strings]   vetor 1: dimensão=768
[lista de strings]   vetor 2: dimensão=768
estratégia usada: lista de strings
norma L2 crua do vetor 0     = 0.589191
cos(gato, cachorro)          = 0.756068
cos(gato, mecânica quântica) = 0.715598
OK: lote devolve um vetor por texto e a similaridade é coerente.
```

Saída idêntica em duas execuções seguidas; código de saída `0`.

### O que ficou provado

| Pergunta | Resposta |
|---|---|
| Lote de N textos devolve N vetores? | **Sim** — 3 textos, 3 vetores, numa única requisição. |
| Foi preciso embrulhar cada texto num `Content`? | **Não.** `contents=["gato", "cachorro", "mecânica quântica"]` bastou. O caminho com `Content` continua no script, como fallback, caso o provedor mude. |
| `output_dimensionality=768` é respeitado? | **Sim** — todos os vetores vieram com 768 posições. |
| O vetor de 768 chega normalizado? | **Não.** A norma L2 crua foi **0.589191**. A normalização manual do adapter não é zelo: sem ela a distância de cosseno da `FEAT-0002` mentiria. |
| `cos(v0,v1) > cos(v0,v2)`? | **Sim** — 0.756068 > 0.715598. |

**Observação para quem for calibrar o `SIMILARITY_THRESHOLD` na `FEAT-0002`:** a margem
entre o par relacionado e o par não relacionado é estreita (0.0405). Palavras soltas
vivem numa região alta e comprimida do espaço deste modelo — 0.7156 entre "gato" e
"mecânica quântica" mostra que **similaridade alta em absoluto não significa
relevância**. O corte precisa ser calibrado contra chunks reais, nunca herdado desses
números.

> **Fechado pela `FEAT-0002 A.5`:** a calibração contra chunks reais foi feita e está
> na seção seguinte. Confirmou o aviso pela metade — a faixa é mesmo alta (positivas
> entre 0,724 e 0,808), mas **frases inteiras separam muito melhor que palavras
> soltas**: contra chunks de verdade a folga entre positivas e negativas é de 0,198,
> quase cinco vezes a margem de 0,0405 medida com palavras isoladas. O limiar saiu
> **0,625**, e não teria como ser adivinhado a partir dos números acima.

---

## `eval/run_eval.py` — qualidade do retrieval e calibração do limiar

**Pergunta:** o retrieval devolve a página certa, recusa o que o documento não
responde, e qual valor de `SIMILARITY_THRESHOLD` separa uma coisa da outra?

**Por que importa:** construir retrieval é fácil; medir é o que diz se ele funciona.
E o `SIMILARITY_THRESHOLD` é a única defesa contra o modelo responder com base nos
"cinco chunks menos ruins" quando o documento simplesmente não tem a resposta — um
número errado aí quebra a fundamentação inteira, em silêncio.

### Como reproduzir

O eval **não ingere o PDF**. Ele recebe o `document_id` de um documento já `ready` —
reingerir a cada rodada queimaria a quota que a calibração precisa gastar olhando os
números várias vezes.

```
# 1. Suba o compose e ingira o Exemplo-YAITEC.pdf uma única vez (pela UI ou pela API).
# 2. Pegue o id:
docker compose exec db psql -U talkdoc -d talkdoc -c \
  "select id, filename, status from documents;"

# 3. Rode, a partir de backend/:
uv run python -m eval.run_eval --document-id <uuid>

# Variações sem editar código:
uv run python -m eval.run_eval --document-id <uuid> --threshold 0.625 --top-k 5
uv run python -m eval.run_eval --document-id <uuid> --sweep 0.55,0.60,0.625,0.70
```

`make eval` roda o mesmo comando sem argumentos, então passe o id pelo ambiente:

```
EVAL_DOCUMENT_ID=<uuid> make eval
```

O relatório sai em `stdout` e o log estruturado em `stderr`, de propósito:
`make eval > eval.md` produz markdown limpo, pronto para colar no README do projeto.
A saída é **não-zero** quando NFR-7 não é cumprido — uma métrica que não pode
reprovar é decoração.

### O dataset (`eval/dataset.json`)

23 perguntas versionadas sobre o `Exemplo-YAITEC.pdf` (3 páginas, 10 chunks) —
eram 16 até o BUG-002 acrescentar as sete sem âncora (última seção deste arquivo):

- **19 positivas**, com `expected_page`, distribuídas pelas três páginas e por tipos
  diferentes de pergunta — fato pontual, número, lista, nome próprio e termo exato
  (o e-mail de contato).
- **10 dessas 19 citam a empresa pelo nome e 9 não** (P11–P16 e as continuações). A
  divisão é o que a `A.5` não tinha e o que o BUG-002 mostrou ser decisiva: o nome
  funciona como âncora e desloca a distribuição inteira para cima.
- **3 dessas 19 são perguntas de continuação**, com `history`: a página só é
  alcançável se a pergunta for reescrita antes da busca.
- **4 negativas**, com `expected_page: null`, sobre assuntos que o documento não
  menciona nem de raspão (receita de bolo, futebol, mecânica de automóvel, dengue).

Duas regras que valeram na escrita do dataset e que o mantêm honesto:

1. **Nenhuma positiva com resposta em duas páginas.** O tema "RAG evita alucinação",
   por exemplo, aparece nas páginas 2 **e** 3 — usá-lo como positiva de página única
   faria a métrica medir o desempate, não o retrieval. Ficou de fora.
2. **O dataset não foi ajustado depois de ver os números.** As perguntas saíram do
   texto extraído, antes da primeira rodada; nenhuma foi trocada para melhorar
   métrica — e a regra valeu de novo para as sete do BUG-002, escritas a partir do
   texto extraído antes da primeira rodada. `tests/test_eval_metrics.py` prende as
   propriedades estruturais (8–20 positivas, 4 negativas, ≥ 3 páginas cobertas, ≥ 1
   continuação) para que um ajuste futuro precise ser deliberado.

### O que cada métrica mede, e por que existe

| métrica | o que mede | por que existe |
|---|---|---|
| `recall@1` | a página certa veio em primeiro? | é o que o usuário vê no chip de citação de cima |
| `recall@3` | a página certa está entre os 3 primeiros chunks? | é a métrica do gate (NFR-7); mede **ordenação** |
| `MRR` | média de `1/posição` do primeiro acerto | recall trata "acertou em 1º" e "acertou em 3º" como iguais; `MRR` não |
| taxa de recusa correta | fração das negativas em que **nenhum** chunk alcançou o limiar | é o contrapeso do recall: sem ela, o limiar ótimo é 0 |
| taxa de falsa recusa | fração das positivas recusadas por engano | é o contrapeso da recusa: sem ela, o limiar ótimo é 1 |
| distribuição (mín/média/máx) por grupo | onde caem as similaridades de cada grupo | é o **único** dado que justifica um valor de limiar antes de escolhê-lo |

**`recall@k` não depende do limiar, e isso é deliberado.** Ele mede o ranking; quem
mede o limiar são as duas taxas de recusa. Misturar os dois é o erro que tornava a
calibração circular (OQ-10): recall melhora monotonicamente quanto mais baixo o
corte, então otimizar por ele empurraria o limiar para zero e destruiria a recusa.

**Por que `recall@3` e não `@5`.** Porque `recall@5` **não pode falhar** neste
documento, e uma métrica que não pode falhar não mede nada. Medido: nas 12 positivas,
o top-5 já contém as três páginas do PDF em todas as 12 — qualquer que fosse a página
esperada, `recall@5` daria 1,000. Com `k=3` a métrica discrimina de verdade: a P02
acertou só na 2ª posição e derrubou o `recall@1` para 0,917.

**Por que as negativas existem.** Sem elas a calibração é circular e o limiar
desaparece: um dataset só de positivas é otimizado por `SIMILARITY_THRESHOLD=0`,
que é exatamente a configuração em que o sistema inventa resposta para pergunta que o
documento não responde. As negativas são o que dá um piso ao corte; a falsa recusa é
o que lhe dá um teto.

### Execução de 2026-08-17 — `document_id` `97959135-49da-4f15-85d9-cfbff1488b3a`

`Exemplo-YAITEC.pdf`, 3 páginas, 10 chunks, `RETRIEVAL_TOP_K=5`. Duas execuções
seguidas devolveram scores idênticos até a terceira casa.

```
## Eval de retrieval — `Exemplo-YAITEC.pdf`

- `document_id`: `97959135-49da-4f15-85d9-cfbff1488b3a`
- chunks no banco: **10**
- `RETRIEVAL_TOP_K`: **5** | `SIMILARITY_THRESHOLD`: **0.625**
- itens: 16 (12 positivas, 4 negativas)

### Por pergunta

| id | grupo | query | esperada | páginas recuperadas | rank | melhor score | recusada? |
|---|---|---|---|---|---|---|---|
| P01 | positive | A YAITEC atende que tipo de mercado? | 1 | p1(0.762), p2(0.733), p1(0.732), p3(0.729), p3(0.728) | 1 | 0.762 | não ✓ |
| P02 | positive | O que os agentes SQL da YAITEC fazem? | 1 | p3(0.724), p1(0.703), p1(0.700), p3(0.685), p2(0.671) | 2 | 0.724 | não ✓ |
| P03 | positive | O que inclui o serviço de consultoria e prototipação da YAITEC? | 1 | p1(0.768), p2(0.737), p3(0.719), p2(0.704), p1(0.704) | 1 | 0.768 | não ✓ |
| P04 | positive | Quem fundou a YAITEC? | 2 | p2(0.768), p2(0.765), p1(0.737), p3(0.727), p3(0.726) | 1 | 0.768 | não ✓ |
| P05 | positive | Quantos projetos e clientes a YAITEC já entregou? | 2 | p2(0.770), p2(0.736), p3(0.724), p1(0.716), p3(0.714) | 1 | 0.770 | não ✓ |
| P06 | positive | Quais empresas estão entre os clientes e parcerias da YAITEC? | 2 | p2(0.788), p2(0.754), p3(0.742), p1(0.737), p3(0.725) | 1 | 0.788 | não ✓ |
| P07 | positive | Quais são os valores da YAITEC? | 2 | p2(0.767), p1(0.755), p1(0.737), p3(0.731), p2(0.729) | 1 | 0.767 | não ✓ |
| P08 | positive | Qual é o e-mail de contato da YAITEC? | 3 | p3(0.748), p1(0.747), p2(0.747), p2(0.740), p3(0.739) | 1 | 0.748 | não ✓ |
| P09 | positive | A atuação da YAITEC é presencial ou remota? | 3 | p3(0.808), p2(0.741), p3(0.733), p1(0.731), p2(0.730) | 1 | 0.808 | não ✓ |
| P10 | positive | Em que cidade o time da YAITEC se reúne no coworking? | 3 | p3(0.773), p2(0.734), p2(0.729), p1(0.717), p3(0.716) | 1 | 0.773 | não ✓ |
| C01 | positive | Quem fundou a YAITEC? e a formação? | 2 | p2(0.765), p2(0.759), p1(0.725), p3(0.723), p1(0.721) | 1 | 0.765 | não ✓ |
| C02 | positive | Onde o time da YAITEC se reúne? e quem mora longe de lá? | 3 | p3(0.729), p2(0.703), p3(0.694), p2(0.692), p1(0.666) | 1 | 0.729 | não ✓ |
| N01 | negative | Qual é a receita do bolo de cenoura com cobertura de chocolate? | — | p1(0.502), p2(0.498), p1(0.491), p3(0.491), p1(0.484) | — | 0.502 | sim ✓ |
| N02 | negative | Quantos gols Pelé marcou pela seleção brasileira? | — | p2(0.476), p3(0.471), p1(0.470), p1(0.468), p2(0.458) | — | 0.476 | sim ✓ |
| N03 | negative | De quanto em quanto tempo devo trocar o óleo do motor do carro? | — | p3(0.526), p3(0.525), p2(0.519), p1(0.512), p1(0.506) | — | 0.526 | sim ✓ |
| N04 | negative | Quais são os sintomas da dengue? | — | p3(0.523), p1(0.517), p1(0.512), p1(0.509), p3(0.507) | — | 0.523 | sim ✓ |

### Continuação: pergunta crua × pergunta condensada

| id | esperada | query crua | rank cru | query condensada | rank condensado |
|---|---|---|---|---|---|
| C01 | 2 | e a formação? | 4 | Quem fundou a YAITEC? e a formação? | 1 |
| C02 | 3 | e quem mora longe de lá? | 1 | Onde o time da YAITEC se reúne? e quem mora longe de lá? | 1 |

### Agregado

| métrica | valor | piso NFR-7 | situação |
|---|---|---|---|
| `recall@1` (positivas) | 0.917 | — | — |
| `recall@3` (positivas) | 1.000 | ≥ 0.80 | ok |
| `MRR` (positivas) | 0.958 | ≥ 0.70 | ok |
| taxa de recusa correta (negativas) | 1.000 | 1.00 | ok |
| taxa de falsa recusa (positivas) | 0.000 | 0.00 | ok |

### Distribuição de similaridade, por grupo

| conjunto | n | mín | média | máx |
|---|---|---|---|---|
| positivas — melhor chunk | 12 | 0.724 | 0.764 | 0.808 |
| negativas — melhor chunk | 4 | 0.476 | 0.507 | 0.526 |
| positivas — todos os chunks do top-k | 60 | 0.666 | 0.733 | 0.808 |
| negativas — todos os chunks do top-k | 20 | 0.458 | 0.498 | 0.526 |

- maior similaridade entre as **negativas**: **0.526**
- menor similaridade entre as **positivas**: **0.724**
- folga entre os dois grupos: **+0.198**
- ponto médio da folga (candidato a `SIMILARITY_THRESHOLD`): **0.625**

### Varredura de limiar (offline, sem custo de quota)

| limiar | recusa correta (negativas) | falsa recusa (positivas) | NFR-7 |
|---|---|---|---|
| 0.456 | 0.000 | 0.000 | **falha** |
| 0.487 | 0.250 | 0.000 | **falha** |
| 0.518 | 0.500 | 0.000 | **falha** |
| 0.549 | 1.000 | 0.000 | ok |
| 0.580 | 1.000 | 0.000 | ok |
| 0.611 | 1.000 | 0.000 | ok |
| 0.642 | 1.000 | 0.000 | ok |
| 0.673 | 1.000 | 0.000 | ok |
| 0.704 | 1.000 | 0.000 | ok |
| 0.735 | 1.000 | 0.167 | **falha** |
| 0.766 | 1.000 | 0.417 | **falha** |
| 0.797 | 1.000 | 0.917 | **falha** |
| 0.828 | 1.000 | 1.000 | **falha** |

### Gate

**NFR-7 ATINGIDO** com `SIMILARITY_THRESHOLD=0.625`.
```

### Por que o limiar é 0,625 (OQ-10, resolvido com número medido)

> **Superado em 2026-08-17 pelo BUG-002.** O limiar vigente é **0,561**; a medição
> que o justifica está na última seção deste arquivo. O raciocínio abaixo continua
> válido como método — o que estava errado era o dataset que o alimentou, não a
> conta.


Os dois grupos não se sobrepõem: a negativa mais parecida com o documento chega a
**0,526** e a positiva mais difícil fica em **0,724**. Existe, portanto, um intervalo
inteiro de limiares que acerta os dois lados — a varredura mostra `NFR-7 ok` de
~0,527 até ~0,724.

Dentro desse intervalo, o valor escolhido é o que fica **mais longe das duas
fronteiras**: `(0,526 + 0,724) / 2 = 0,625`, com ~0,099 de margem de cada lado. O
critério não é "maximizar recall" — recall nem se mexe ao longo da varredura — e sim
**sobreviver à próxima pergunta que ninguém escreveu ainda**: uma pergunta legítima
um pouco mais difícil que a P02, ou uma pergunta de fora um pouco mais próxima do
tema, precisa cair do lado certo.

O `0.55` que estava no `.env.example` era palpite, e a medição mostra o tamanho do
risco que ele carregava: ficava a **0,024** da negativa mais próxima (a N03, "troca
de óleo", em 0,526). Uma única pergunta de fora um pouco mais temática já teria
passado pelo corte e o sistema responderia com aparência de fundamento. Ele "passava"
no eval por sorte, não por margem.

**Depois de trocar o valor, sincronize o seu `.env` local com o `.env.example`** —
o `.env` não é versionado, e o eval mede o que estiver nele.

### Limitações honestas destes números

- **A amostra é pequena**: 12 positivas e 4 negativas. `recall@3 = 1,000` não é
  "retrieval perfeito"; é "nenhuma das 12 falhou". Uma falha custaria 0,083.
- **A folga de 0,198 é desta combinação** de documento, dataset e modelo. Documento
  maior, com páginas que tratam do mesmo assunto, comprime a distribuição das
  positivas para baixo — o limiar precisa ser remedido, não herdado.
- **A condensação usada aqui é o fallback determinístico** (`should_condense` +
  `fallback_query`), não a reescrita por LLM da fase A.4: é o caminho sem quota e sem
  variância entre rodadas. A reescrita do modelo só pode ser melhor que concatenar as
  duas perguntas, então C01 e C02 medem um **piso**, não um teto otimista.
- **C02 já acertava sem condensar** ("e quem mora longe de lá?" recupera a página 3
  sozinha, porque "mora"/"longe" batem no trecho sobre trabalho remoto). Quem prova o
  ponto é a **C01**: crua ela cai para a 4ª posição, condensada volta para a 1ª.
- **A busca densa borra termo exato**, e dá para ver aqui: na P08 (e-mail de contato)
  o primeiro colocado ganha por 0,001 do segundo (0,748 × 0,747), e na P02 a página 3
  — que só **cita** "agentes SQL" numa lista — passou na frente da página 1, que é
  onde o serviço está de fato descrito. É exatamente o sintoma que a fase A.7 (busca
  híbrida com fusão RRF) existe para tratar.

---

## Fase `A.7` — busca híbrida com fusão RRF: antes e depois

**Resumo:** no dataset de avaliação o delta é **zero** — as seis métricas e as
tabelas por pergunta saem byte a byte idênticas. Em consulta por **termo
literal**, que o dataset não contém, a fusão conserta o que a busca densa perde.
As duas coisas são resultado, e as duas estão registradas aqui.

### Como as duas medições foram feitas

A baseline foi **remedida**, e não copiada da rodada da `A.5`. O motivo é que a
`A.7` altera o schema (`tsv` gerada e índice GIN em `chunks`) e exige `make down`
com reingestão: comparar o "depois" contra números medidos sobre um
`document_id` que deixou de existir misturaria duas variáveis — a fusão e uma
ingestão diferente.

A sequência foi: `make down` → schema novo → reingestão do `Exemplo-YAITEC.pdf`
(`document_id` `89774e1c-009d-47c5-80e4-ba6c7324f3d3`, 10 chunks, 3 páginas) →
`make eval` **sem** `--hybrid` (baseline) → fusão ligada → `make eval`
**com** `--hybrid`. Mesmo corpus, mesmo dataset, mesmo limiar, **mesmo caminho
de código**: a flag decide só se a via lexical entra na fusão.

```
EVAL_DOCUMENT_ID=89774e1c-… uv run python -m eval.run_eval --threshold 0.625
EVAL_DOCUMENT_ID=89774e1c-… uv run python -m eval.run_eval --threshold 0.625 --hybrid
```

### O delta no dataset: zero

| métrica | densa (baseline) | híbrida | delta |
|---|---|---|---|
| `recall@1` (positivas) | 0.917 | 0.917 | **0.000** |
| `recall@3` (positivas) | 1.000 | 1.000 | **0.000** |
| `MRR` (positivas) | 0.958 | 0.958 | **0.000** |
| taxa de recusa correta (negativas) | 1.000 | 1.000 | 0.000 |
| taxa de falsa recusa (positivas) | 0.000 | 0.000 | 0.000 |

`diff` das tabelas por pergunta das duas execuções: **vazio**. Nenhuma posição
mudou em nenhum dos 16 itens.

**Por que zero, e não negativo — medido, não suposto.**

> *Correção de 2026-08-17.* A primeira redação desta seção dizia que "a via
> lexical devolve mais ou menos o mesmo conjunto que a densa, e o RRF confirma a
> ordem que já existia". Era plausível e estava errada. A medição direta abaixo
> mostra o que de fato acontece, e a causa é mais ampla do que parecia.

`plainto_tsquery` liga os termos da pergunta com **E**, não com OU: para casar,
**todos** eles precisam estar no mesmo chunk. Numa pergunta em linguagem natural
isso quase nunca acontece num trecho de 500 caracteres — "O que os agentes SQL da
YAITEC fazem?" vira `'agent' & 'sql' & 'yaitec' & 'faz'`, e o trecho que descreve
os agentes SQL não contém as quatro.

Contando as linhas que `search_chunks_lexical` devolve para cada item do dataset,
contra o mesmo documento da medição:

| resultado da via lexical | itens |
|---|---|
| **0 linhas** | 13 de 16 |
| 1 linha | 3 (P02, P04, P09) |

Nos 13, a fusão é um **no-op estrito**: com a lista lexical vazia, o RRF devolve a
densa intacta. Nos outros três, o único chunk encontrado era **já o primeiro
colocado da busca densa** — P02 e P09 casaram o chunk 8 (página 3), P04 o chunk 5
(página 2), e as três páginas são exatamente as que a densa já trazia em primeiro
lugar. O RRF reforçou uma ordem que já existia.

É por isso que o `diff` saiu byte a byte idêntico: não é coincidência de duas
listas parecidas, é a fusão não tendo o que acrescentar em nenhum dos 16 casos.

Um segundo obstáculo, mais estreito, se soma ao primeiro no caso do e-mail: o
parser do Postgres trata `contato@yaitec.com` como **um token atômico** e não o
quebra em "contato" + domínio, então nem a palavra "contato" da pergunta alcança
aquele chunk. Medido:

```
to_tsvector('portuguese', '… contato@yaitec.com · João Pessoa, PB')
  -> 'contato@yaitec.com':4 'joã':5 'pb':7 'pesso':6 'solutions':2 'yaitec':1
plainto_tsquery('portuguese', 'qual o e-mail de contato?')
  -> 'e-mail' & 'mail' & 'contat'          casa? f
plainto_tsquery('portuguese', 'contato@yaitec.com')
  -> 'contato@yaitec.com'                  casa? t
```

O teto do dataset também é apertado — `recall@3` já era 1,000 e o `MRR` 0,958 —,
mas ele não é a explicação: a explicação é que a via lexical não entregou nada
para fundir.

### O caso que o dataset não exercita, e onde a fusão morde

O motivo declarado da fase é o termo exato. Medido no mesmo documento, com a API
real, comparando os dois modos da mesma busca:

| consulta | posição do trecho que contém o termo — densa | híbrida |
|---|---|---|
| `contato@yaitec.com` | **ausente do top-3** | **2ª** |
| `UFPB` | 2ª | **1ª** |
| `StartStak` | 1ª | 1ª (a densa já acertava) |

A primeira linha é o achado: perguntando pelo **endereço literal**, a busca
densa não traz o trecho que o contém em lugar nenhum do top-3 — ela traz três
trechos que *falam de contato*. É o mesmo sintoma que a `A.5` já tinha medido de
outro ângulo, quando a página do e-mail ganhou a primeira posição por 0,001: a
similaridade de cosseno não distingue "menciona o assunto" de "contém o dado".

**O alcance disso é estreito, e vale dizer com todas as letras:** as três
consultas da tabela são o **termo colado sozinho**. Perguntando *sobre* o termo
em linguagem natural — "qual o e-mail de contato?" — a via lexical devolve vazio,
pelo motivo da seção anterior, e a resposta sai pela densa (que, nesse caso,
acerta a página). A fusão ajuda quem cola o dado, não quem pergunta por ele.

### Conclusão e o que isso significa para o dataset

A fusão foi **mantida**. O critério da spec manda reverter se o delta for
negativo; ele é zero, e o mecanismo tem ganho medido fora do dataset. O custo é
uma segunda consulta ao banco por turno, no mesmo pool e sem chamada de rede
extra.

O caminho de conserto, se alguém quiser que a fusão morda também na pergunta
natural, é o construtor da query e não a fusão: `websearch_to_tsquery` (que não
força o `AND` entre todos os termos) ou uma query montada com `OR`, mantendo o
`ts_rank_cd` para ordenar. É mudança pequena com efeito grande, e é escopo novo
sobre uma fase já fechada — fica como próximo passo, não como dívida escondida.

Fica registrada uma limitação do dataset, que é o segundo achado mais útil desta
fase para quem vier depois: **as 16 perguntas não incluem nenhuma consulta por
termo literal**, e por isso as métricas da `A.5` não conseguiam ver o problema que a
`A.7` existe para resolver — nem podem medir a solução. Acrescentar duas
perguntas literais (o e-mail e uma sigla) mudaria isso, e mudaria o `recall@1`
da baseline para baixo, que é o que tornaria o delta visível. Não foi feito
aqui de propósito: mexer no dataset **no meio** de uma medição de antes e depois
é exatamente o que a `A.5` proíbe ("não ajustar o dataset para inflar a
métrica").


---

## BUG-002 — recalibração do limiar com positivas sem âncora

**Resumo:** o limiar caiu de **0,625** para **0,561**. Nada mudou no código do
retrieval; o que mudou foi o dataset, que passou a conter as perguntas que o owner
de fato digitou no teste de ponta a ponta. Elas mostram um piso de similaridade
0,128 abaixo do que as perguntas ancoradas mostravam.

### O que estava errado, e não era a conta

As 12 positivas originais mencionam **"YAITEC" explicitamente** — *"Qual é o e-mail
de contato da YAITEC?"*, *"Quais são os valores da YAITEC?"*. O nome da empresa
aparece em quase todos os chunks de um documento institucional e funciona como
âncora que empurra a similaridade para cima. Quem usa escreve *"Qual o e-mail de
contato?"*, sem a âncora — e aí a similaridade cai para a faixa 0,53–0,62, que o
eval da `A.5` declarou vazia.

A folga de 0,198 não era vazia. Ela era ocupada pela forma como gente de verdade
pergunta, e o eval não a via porque nenhuma pergunta do dataset era assim.

Vale registrar que a própria fase `A.7` tinha apontado o buraco, na última seção
acima: *"as 16 perguntas não incluem nenhuma consulta por termo literal ...
acrescentar duas perguntas literais (o e-mail e uma sigla) mudaria isso"*. É
exatamente o que a P11 e a P12 são. Ali a mudança foi recusada porque mexer no
dataset **no meio** de uma medição de antes e depois invalida a comparação; aqui
ela é o objetivo da medição.

### O que entrou no dataset

Sete positivas novas, escritas a partir do texto extraído e **antes** da primeira
rodada — nenhuma foi trocada depois de ver os números, que é a regra que mantém o
dataset honesto:

| id | pergunta | página | por que ela existe |
|---|---|---|---|
| P11 | Qual o e-mail de contato? | 3 | a P08 sem a âncora; é a pergunta que o owner digitou |
| P12 | O que é a UFPB no documento? | 2 | sigla, sem âncora; a outra pergunta recusada no teste |
| P13 | Que tipo de mercado é atendido? | 1 | a P01 sem a âncora |
| P14 | Quantos projetos já foram entregues? | 2 | a P05 sem a âncora |
| P15 | O trabalho é presencial ou remoto? | 3 | a P09 sem a âncora |
| P16 | Quem é o fundador? | 2 | a P04 sem a âncora |
| C03 | e a formação dele? | 2 | continuação com forma contraída — exercita o fix do BUG-001 |

O dataset passou de 16 para 23 itens (19 positivas, 4 negativas). O teto de
positivas em `tests/test_eval_metrics.py` subiu de 12 para 20 junto.

### A medição

`Exemplo-YAITEC.pdf`, `document_id` `ce4e9cd0-fa3a-45e4-852d-5103b73fb736`, 10
chunks, `RETRIEVAL_TOP_K=5`. Primeira rodada ainda com `SIMILARITY_THRESHOLD=0.625`,
para ver o estrago; segunda com `0.561`, que é a que segue abaixo.

```
## Eval de retrieval — `Exemplo-YAITEC.pdf`

- `document_id`: `ce4e9cd0-fa3a-45e4-852d-5103b73fb736`
- chunks no banco: **10**
- `RETRIEVAL_TOP_K`: **5** | `SIMILARITY_THRESHOLD`: **0.561**
- itens: 23 (19 positivas, 4 negativas)

### Por pergunta

| id | grupo | query | esperada | páginas recuperadas | rank | melhor score | recusada? |
|---|---|---|---|---|---|---|---|
| P01 | positive | A YAITEC atende que tipo de mercado? | 1 | p1(0.762), p2(0.733), p1(0.732), p3(0.729), p3(0.728) | 1 | 0.762 | não ✓ |
| P02 | positive | O que os agentes SQL da YAITEC fazem? | 1 | p3(0.724), p1(0.703), p1(0.700), p3(0.685), p2(0.671) | 2 | 0.724 | não ✓ |
| P03 | positive | O que inclui o serviço de consultoria e prototipação da YAITEC? | 1 | p1(0.768), p2(0.737), p3(0.719), p2(0.704), p1(0.704) | 1 | 0.768 | não ✓ |
| P04 | positive | Quem fundou a YAITEC? | 2 | p2(0.768), p2(0.765), p1(0.737), p3(0.727), p3(0.726) | 1 | 0.768 | não ✓ |
| P05 | positive | Quantos projetos e clientes a YAITEC já entregou? | 2 | p2(0.770), p2(0.736), p3(0.724), p1(0.716), p3(0.714) | 1 | 0.770 | não ✓ |
| P06 | positive | Quais empresas estão entre os clientes e parcerias da YAITEC? | 2 | p2(0.788), p2(0.754), p3(0.742), p1(0.737), p3(0.725) | 1 | 0.788 | não ✓ |
| P07 | positive | Quais são os valores da YAITEC? | 2 | p2(0.767), p1(0.755), p1(0.737), p3(0.731), p2(0.729) | 1 | 0.767 | não ✓ |
| P08 | positive | Qual é o e-mail de contato da YAITEC? | 3 | p3(0.748), p1(0.747), p2(0.747), p2(0.740), p3(0.739) | 1 | 0.748 | não ✓ |
| P09 | positive | A atuação da YAITEC é presencial ou remota? | 3 | p3(0.808), p2(0.741), p3(0.733), p1(0.731), p2(0.730) | 1 | 0.808 | não ✓ |
| P10 | positive | Em que cidade o time da YAITEC se reúne no coworking? | 3 | p3(0.773), p2(0.734), p2(0.729), p1(0.717), p3(0.716) | 1 | 0.773 | não ✓ |
| P11 | positive | Qual o e-mail de contato? | 3 | p3(0.596), p3(0.594), p1(0.589), p1(0.585), p2(0.580) | 1 | 0.596 | não ✓ |
| P12 | positive | O que é a UFPB no documento? | 2 | p1(0.612), p1(0.605), p2(0.604), p2(0.597), p2(0.593) | 3 | 0.612 | não ✓ |
| P13 | positive | Que tipo de mercado é atendido? | 1 | p1(0.688), p1(0.663), p1(0.652), p3(0.647), p1(0.635) | 1 | 0.688 | não ✓ |
| P14 | positive | Quantos projetos já foram entregues? | 2 | p2(0.647), p2(0.610), p2(0.609), p1(0.607), p1(0.605) | 1 | 0.647 | não ✓ |
| P15 | positive | O trabalho é presencial ou remoto? | 3 | p3(0.710), p3(0.610), p1(0.608), p1(0.590), p2(0.585) | 1 | 0.710 | não ✓ |
| P16 | positive | Quem é o fundador? | 2 | p2(0.673), p2(0.655), p3(0.625), p2(0.616), p1(0.616) | 1 | 0.673 | não ✓ |
| C01 | positive | Quem fundou a YAITEC? e a formação? | 2 | p2(0.765), p2(0.759), p1(0.725), p3(0.723), p1(0.721) | 1 | 0.765 | não ✓ |
| C02 | positive | Onde o time da YAITEC se reúne? e quem mora longe de lá? | 3 | p3(0.729), p2(0.703), p3(0.694), p2(0.692), p1(0.666) | 1 | 0.729 | não ✓ |
| C03 | positive | Quem fundou a YAITEC? e a formação dele? | 2 | p2(0.764), p2(0.761), p1(0.715), p3(0.709), p1(0.709) | 1 | 0.764 | não ✓ |
| N01 | negative | Qual é a receita do bolo de cenoura com cobertura de chocolate? | — | p1(0.502), p2(0.498), p1(0.491), p3(0.491), p1(0.484) | — | 0.502 | sim ✓ |
| N02 | negative | Quantos gols Pelé marcou pela seleção brasileira? | — | p2(0.476), p3(0.471), p1(0.470), p1(0.468), p2(0.458) | — | 0.476 | sim ✓ |
| N03 | negative | De quanto em quanto tempo devo trocar o óleo do motor do carro? | — | p3(0.526), p3(0.525), p2(0.519), p1(0.512), p1(0.506) | — | 0.526 | sim ✓ |
| N04 | negative | Quais são os sintomas da dengue? | — | p3(0.523), p1(0.517), p1(0.512), p1(0.509), p3(0.507) | — | 0.523 | sim ✓ |

### Continuação: pergunta crua × pergunta condensada

| id | esperada | query crua | rank cru | query condensada | rank condensado |
|---|---|---|---|---|---|
| C01 | 2 | e a formação? | 4 | Quem fundou a YAITEC? e a formação? | 1 |
| C02 | 3 | e quem mora longe de lá? | 1 | Onde o time da YAITEC se reúne? e quem mora longe de lá? | 1 |
| C03 | 2 | e a formação dele? | 1 | Quem fundou a YAITEC? e a formação dele? | 1 |

### Agregado

| métrica | valor | piso NFR-7 | situação |
|---|---|---|---|
| `recall@1` (positivas) | 0.895 | — | — |
| `recall@3` (positivas) | 1.000 | ≥ 0.80 | ok |
| `MRR` (positivas) | 0.939 | ≥ 0.70 | ok |
| taxa de recusa correta (negativas) | 1.000 | 1.00 | ok |
| taxa de falsa recusa (positivas) | 0.000 | 0.00 | ok |

### Distribuição de similaridade, por grupo

| conjunto | n | mín | média | máx |
|---|---|---|---|---|
| positivas — melhor chunk | 19 | 0.596 | 0.729 | 0.808 |
| negativas — melhor chunk | 4 | 0.476 | 0.507 | 0.526 |
| positivas — todos os chunks do top-k | 95 | 0.580 | 0.697 | 0.808 |
| negativas — todos os chunks do top-k | 20 | 0.458 | 0.498 | 0.526 |

- maior similaridade entre as **negativas**: **0.526**
- menor similaridade entre as **positivas**: **0.596**
- folga entre os dois grupos: **+0.070**
- ponto médio da folga (candidato a `SIMILARITY_THRESHOLD`): **0.561**

### Varredura de limiar (offline, sem custo de quota)

| limiar | recusa correta (negativas) | falsa recusa (positivas) | NFR-7 |
|---|---|---|---|
| 0.456 | 0.000 | 0.000 | **falha** |
| 0.487 | 0.250 | 0.000 | **falha** |
| 0.518 | 0.500 | 0.000 | **falha** |
| 0.549 | 1.000 | 0.000 | ok |
| 0.580 | 1.000 | 0.000 | ok |
| 0.611 | 1.000 | 0.053 | **falha** |
| 0.642 | 1.000 | 0.105 | **falha** |
| 0.673 | 1.000 | 0.158 | **falha** |
| 0.704 | 1.000 | 0.263 | **falha** |
| 0.735 | 1.000 | 0.421 | **falha** |
| 0.766 | 1.000 | 0.632 | **falha** |
| 0.797 | 1.000 | 0.947 | **falha** |
| 0.828 | 1.000 | 1.000 | **falha** |

### Gate

**NFR-7 ATINGIDO** com `SIMILARITY_THRESHOLD=0.561`.
```

### Por que 0,561

Mesmo critério da `A.5`, com números novos: os dois grupos **continuam sem se
sobrepor** — a negativa mais alta fica em **0,526** e a positiva mais baixa em
**0,596** —, e o valor escolhido é o meio dessa folga, `(0,526 + 0,596) / 2 =
0,561`, com ~0,035 de margem para cada lado.

O terceiro caminho que o relato do BUG-002 previa — *"se a folga sumir, a decisão é
arquitetural"* — **não** se materializou. A folga encolheu de 0,198 para 0,070, o
que é bem menos confortável, mas o limiar sozinho ainda separa os dois grupos. Não
há motivo para trazer reranking ou segunda condição de recusa para dentro desta
entrega.

Com 0,625, duas positivas eram recusadas por engano (P11 em 0,596 e P12 em 0,612) —
taxa de falsa recusa de 0,105, e o gate NFR-7 reprovava. Com 0,561, as duas taxas
voltam a zero.

### O que a margem menor significa

- **0,035 de folga de cada lado é apertado**, e é honesto dizer isso. Uma negativa
  um pouco mais temática que a N03 ("troca de óleo", 0,526) ou uma positiva um
  pouco mais difícil que a P11 (0,596) cai do lado errado. A margem de 0,10 do
  valor anterior era ilusória: media a distância entre negativas de fora do
  assunto e positivas com âncora, dois grupos que o uso real não produz.
- **O que compraria margem de volta** é aumentar a separação, não mover o corte:
  reranking, ou a query lexical menos restritiva que a `A.7` já deixou apontada
  (`websearch_to_tsquery` no lugar do `AND` entre todos os termos). Fica registrado
  como próximo passo medido, não como dívida escondida.
- **`recall@1` caiu de 0,917 para 0,895** e o `MRR` de 0,958 para 0,939. Não é
  regressão do retrieval: são sete perguntas mais difíceis entrando na conta. A
  única que erra a primeira posição entre as novas é a P12 (rank 3) — a sigla
  "UFPB" aparece uma vez só, e a busca densa borra termo exato, que é o sintoma
  conhecido desde a `A.5`.
- **A C03 confirma o fix do BUG-001 pelo lado do retrieval:** crua, *"e a formação
  dele?"* já vinha em 1º neste documento; o que o fix garante é que ela **seja
  condensada** antes de chegar aqui — sem isso, `should_condense` devolvia `False`
  e a query crua ia para a busca no chat de verdade, onde pontuou 0,527 e foi
  recusada.
