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
# 1. Suba o compose e ingira o samples/lgpd-capitulos-1-2.pdf uma única vez (UI ou API).
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

25 perguntas versionadas sobre o `samples/lgpd-capitulos-1-2.pdf` (12 páginas,
91 chunks):

- **19 positivas**, com `expected_page`, espalhadas por **11 das 12 páginas** e por
  tipos diferentes de pergunta — fato pontual, lista e termo exato.
- **10 dessas 19 citam o número do artigo e 9 não** (P11–P16 e as continuações). A
  divisão é o que o BUG-002 mostrou ser decisiva: o número do artigo funciona como
  âncora lexical e desloca a distribuição inteira para cima. É também o que separa
  o que a fusão com a busca lexical resolve do que só a busca vetorial alcança.
- **3 dessas 19 são perguntas de continuação**, com `history`: a página só é
  alcançável se a pergunta for reescrita antes da busca.
- **6 negativas**, com `expected_page: null`, em duas famílias. Três estão
  completamente fora do documento (receita de bolo, mecânica de automóvel, dengue).
  As outras três são assuntos da **própria LGPD** que ficaram fora dos Capítulos I e
  II: sanções administrativas (art. 52), comunicação de incidente de segurança
  (art. 48) e revisão de decisão automatizada (art. 20). Estas são as que importam —
  o vocabulário é idêntico ao do documento.

Duas regras que valeram na escrita do dataset e que o mantêm honesto:

1. **Nenhuma positiva com resposta em duas páginas.** O tema "RAG evita alucinação",
   por exemplo, aparece nas páginas 2 **e** 3 — usá-lo como positiva de página única
   faria a métrica medir o desempate, não o retrieval. Ficou de fora.
2. **O dataset não foi ajustado depois de ver os números.** As perguntas saíram do
   texto extraído, antes da primeira rodada; nenhuma foi trocada para melhorar
   métrica. Houve **uma** troca, e ela foi no sentido contrário: duas negativas
   candidatas — transferência internacional e competências da ANPD — foram
   descartadas porque o chat real **respondeu as duas, corretamente**. O art. 5º
   define os dois termos e o art. 4º trata de dados vindos do exterior, então o
   documento responde parcialmente a ambas. Negativa que o documento responde não
   mede recusa; mede erro de rótulo, e infla a métrica a favor de quem escreveu o
   dataset. `tests/test_eval_metrics.py` prende as propriedades estruturais (8–20
   positivas, 4–10 negativas, ≥ 3 delas fora do documento, ≥ 3 páginas cobertas,
   ≥ 1 continuação) para que um ajuste futuro precise ser deliberado.
3. **O gabarito de página foi medido, não presumido.** Cada `expected_page` saiu de
   uma busca literal pela resposta no texto que o `pypdf` extrai de cada página — o
   mesmo texto que a ingestão recebe. Gabarito tirado do layout do PDF mediria o
   gerador de PDF, não o retrieval.

### O que cada métrica mede, e por que existe

| métrica | o que mede | por que existe |
|---|---|---|
| `recall@1` | a página certa veio em primeiro? | é o que o usuário vê no chip de citação de cima |
| `recall@3` | a página certa está entre os 3 primeiros chunks? | é a métrica do gate (NFR-7); mede **ordenação** |
| `MRR` | média de `1/posição` do primeiro acerto | recall trata "acertou em 1º" e "acertou em 3º" como iguais; `MRR` não |
| recusa correta — fora do documento | fração das negativas **sem relação com o documento** em que nenhum chunk alcançou o limiar | é o contrapeso do recall: sem ela, o limiar ótimo é 0. É o que o gate cobra |
| recusa correta — todas as negativas | a mesma taxa, incluindo as de mesmo vocabulário | informativa: ver "A sobreposição que nenhum limiar resolve" |
| taxa de falsa recusa | fração das positivas recusadas por engano | é o contrapeso da recusa: sem ela, o limiar ótimo é 1 |
| distribuição (mín/média/máx) por grupo | onde caem as similaridades de cada grupo | é o **único** dado que justifica um valor de limiar antes de escolhê-lo |

**`recall@k` não depende do limiar, e isso é deliberado.** Ele mede o ranking; quem
mede o limiar são as duas taxas de recusa. Misturar os dois é o erro que tornava a
calibração circular (OQ-10): recall melhora monotonicamente quanto mais baixo o
corte, então otimizar por ele empurraria o limiar para zero e destruiria a recusa.

**Por que `recall@3` e não `@5`.** A escolha nasceu com o documento anterior, de três
páginas, onde `recall@5` **não podia falhar**: o top-5 continha o documento inteiro, e
uma métrica que não pode falhar não mede nada. Com 12 páginas e 91 chunks o argumento
perdeu força — mas `k=3` continua sendo o corte certo, por outro motivo: a interface
mostra cinco chips de citação, e a página que importa precisa estar entre os primeiros
para que quem lê a encontre sem caçar.

**Por que as negativas existem.** Sem elas a calibração é circular e o limiar
desaparece: um dataset só de positivas é otimizado por `SIMILARITY_THRESHOLD=0`,
que é exatamente a configuração em que o sistema inventa resposta para pergunta que o
documento não responde. As negativas são o que dá um piso ao corte; a falsa recusa é
o que lhe dá um teto.

---

## Execução de 2026-09-10 — `samples/lgpd-capitulos-1-2.pdf`

12 páginas, 91 chunks, `RETRIEVAL_TOP_K=5`, `SIMILARITY_THRESHOLD=0.605`,
`gemini-embedding-001` a 768 dimensões, busca híbrida ligada.

### Por pergunta

| id | grupo | query | esperada | páginas recuperadas | rank | melhor score | recusada? |
|---|---|---|---|---|---|---|---|
| P01 | positive | Qual é o objeto da Lei nº 13.709, segundo o art. 1º? | 1 | p1(0.751), p1(0.719), p12(0.714), p10(0.700), p4(0.698) | 1 | 0.751 | não ✓ |
| P02 | positive | A quais tratamentos de dados a Lei não se aplica, conforme o art. 4º? | 2 | p2(0.837), p2(0.779), p1(0.747), p2(0.742), p1(0.742) | 1 | 0.837 | não ✓ |
| P03 | positive | Como o art. 5º define banco de dados? | 3 | p3(0.734), p2(0.727), p3(0.723), p2(0.718), p2(0.703) | 1 | 0.734 | não ✓ |
| P04 | positive | Como o art. 5º define a autoridade nacional? | 4 | p4(0.718), p4(0.707), p4(0.697), p1(0.684), p3(0.681) | 1 | 0.718 | não ✓ |
| P05 | positive | Quais princípios o art. 6º manda observar no tratamento de dados pessoais? | 5 | p5(0.839), p6(0.769), p6(0.764), p5(0.755), p5(0.744) | 1 | 0.839 | não ✓ |
| P06 | positive | Em quais hipóteses o art. 7º autoriza o tratamento de dados pessoais? | 6 | p6(0.820), p6(0.746), p2(0.743), p6(0.732), p8(0.731) | 1 | 0.820 | não ✓ |
| P07 | positive | De que forma o consentimento deve ser fornecido segundo o art. 8º? | 7 | p7(0.792), p7(0.721), p7(0.712), p7(0.708), p6(0.707) | 1 | 0.792 | não ✓ |
| P08 | positive | Em que situações o art. 11 permite o tratamento de dados pessoais sensíveis? | 8 | p8(0.796), p8(0.745), p8(0.740), p8(0.735), p2(0.715) | 1 | 0.796 | não ✓ |
| P09 | positive | O que o art. 12 diz sobre dados anonimizados? | 10 | p10(0.823), p10(0.750), p12(0.741), p10(0.727), p10(0.720) | 1 | 0.823 | não ✓ |
| P10 | positive | Como o art. 14 trata os dados pessoais de crianças e adolescentes? | 11 | p11(0.826), p11(0.754), p11(0.744), p11(0.723), p11(0.716) | 1 | 0.826 | não ✓ |
| P11 | positive | Quem é a pessoa indicada para ser o canal de comunicação entre o controlador e os titulares? | 3 | p3(0.801), p3(0.780), p3(0.705), p3(0.678), p6(0.661) | 1 | 0.801 | não ✓ |
| P12 | positive | Quais são os princípios que devem ser observados no tratamento de dados pessoais? | 5 | p5(0.801), p5(0.789), p5(0.781), p5(0.775), p6(0.756) | 1 | 0.801 | não ✓ |
| P13 | positive | O que o controlador precisa fazer quando trata dados com base no legítimo interesse? | 8 | p8(0.791), p8(0.769), p8(0.767), p7(0.711), p6(0.709) | 1 | 0.791 | não ✓ |
| P14 | positive | O titular tem direito a consulta facilitada sobre o tratamento dos seus dados? | 7 | p7(0.768), p7(0.747), p5(0.744), p7(0.708), p7(0.707) | 1 | 0.768 | não ✓ |
| P15 | positive | Quando termina o tratamento de dados pessoais? | 12 | p12(0.792), p12(0.733), p3(0.728), p7(0.710), p5(0.709) | 1 | 0.792 | não ✓ |
| P16 | positive | Quais são os fundamentos da proteção de dados pessoais? | 1 | p1(0.766), p8(0.739), p5(0.729), p5(0.729), p5(0.726) | 1 | 0.766 | não ✓ |
| C01 | positive | O que é o princípio da necessidade? e o da finalidade? | 5 | p5(0.669), p5(0.645), p6(0.640), p1(0.619), p7(0.616) | 1 | 0.669 | não ✓ |
| C02 | positive | e nesse caso vale para crianças? | 11 | p11(0.731), p11(0.730), p11(0.712), p11(0.710), p11(0.703) | 1 | 0.731 | não ✓ |
| C03 | positive | Quem é o operador no tratamento de dados? e a definição dele? | 3 | p3(0.767), p3(0.763), p3(0.708), p3(0.708), p3(0.700) | 1 | 0.767 | não ✓ |
| N01 | negative | Qual é a receita do bolo de cenoura com cobertura de chocolate? | — | p1(0.510), p1(0.509), p7(0.507), p1(0.506), p1(0.501) | — | 0.510 | sim ✓ |
| N02 | negative | De quanto em quanto tempo devo trocar o óleo do motor do carro? | — | p1(0.539), p7(0.530), p1(0.530), p3(0.529), p1(0.524) | — | 0.539 | sim ✓ |
| N03 | negative | Quais são os sintomas da dengue? | — | p1(0.539), p8(0.531), p4(0.527), p1(0.526), p4(0.525) | — | 0.539 | sim ✓ |
| N04 | negative | Quais são as sanções administrativas aplicáveis por infração a esta Lei? | — | p1(0.668), p4(0.667), p4(0.662), p2(0.658), p2(0.657) | — | 0.668 | **não ✗** |
| N05 | negative | Em quanto tempo o controlador deve comunicar um incidente de segurança à autoridade nacional? | — | p3(0.653), p2(0.644), p3(0.640), p2(0.639), p8(0.618) | — | 0.653 | **não ✗** |
| N06 | negative | O titular pode solicitar a revisão de decisões tomadas exclusivamente de forma automatizada? | — | p7(0.644), p2(0.639), p7(0.635), p8(0.634), p7(0.633) | — | 0.644 | **não ✗** |

### Continuação: pergunta crua × pergunta condensada

| id | esperada | query crua | rank cru | query condensada | rank condensado |
|---|---|---|---|---|---|
| C01 | 5 | e o da finalidade? | 2 | O que é o princípio da necessidade? e o da finalidade? | 1 |
| C02 | 11 | e nesse caso vale para crianças? | 1 | e nesse caso vale para crianças? | 1 |
| C03 | 3 | e a definição dele? | 2 | Quem é o operador no tratamento de dados? e a definição dele? | 1 |

### Agregado

| métrica | valor | piso NFR-7 | situação |
|---|---|---|---|
| `recall@1` (positivas) | 1.000 | — | — |
| `recall@3` (positivas) | 1.000 | ≥ 0.80 | ok |
| `MRR` (positivas) | 1.000 | ≥ 0.70 | ok |
| recusa correta — fora do documento | 1.000 | 1.00 | ok |
| recusa correta — todas as negativas | 0.500 | — | informativa |
| taxa de falsa recusa (positivas) | 0.000 | 0.00 | ok |

### Distribuição de similaridade, por grupo

| conjunto | n | mín | média | máx |
|---|---|---|---|---|
| positivas — melhor chunk | 19 | 0.669 | 0.780 | 0.839 |
| negativas — melhor chunk | 6 | 0.510 | 0.592 | 0.668 |
| positivas — todos os chunks do top-k | 95 | 0.616 | 0.735 | 0.839 |
| negativas — todos os chunks do top-k | 30 | 0.501 | 0.584 | 0.668 |

- maior similaridade entre as **negativas**: **0.668**
- menor similaridade entre as **positivas**: **0.669**
- folga entre os dois grupos: **+0.001**
- ponto médio da folga (candidato a `SIMILARITY_THRESHOLD`): **0.669**

### Varredura de limiar (offline, sem custo de quota)

| limiar | recusa fora do documento | recusa de todas as negativas | falsa recusa (positivas) | NFR-7 |
|---|---|---|---|---|
| 0.490 | 0.000 | 0.000 | 0.000 | **falha** |
| 0.521 | 0.333 | 0.167 | 0.000 | **falha** |
| 0.551 | 1.000 | 0.500 | 0.000 | ok |
| 0.582 | 1.000 | 0.500 | 0.000 | ok |
| 0.613 | 1.000 | 0.500 | 0.000 | ok |
| 0.644 | 1.000 | 0.500 | 0.000 | ok |
| 0.674 | 1.000 | 1.000 | 0.053 | **falha** |
| 0.705 | 1.000 | 1.000 | 0.053 | **falha** |
| 0.736 | 1.000 | 1.000 | 0.211 | **falha** |
| 0.767 | 1.000 | 1.000 | 0.316 | **falha** |
| 0.797 | 1.000 | 1.000 | 0.632 | **falha** |
| 0.828 | 1.000 | 1.000 | 0.895 | **falha** |
| 0.859 | 1.000 | 1.000 | 1.000 | **falha** |

### Gate

**NFR-7 ATINGIDO** com `SIMILARITY_THRESHOLD=0.605`.

### Por que o limiar é 0,605

A varredura acima tem três faixas, e o valor escolhido é o meio da única que
serve:

| faixa | o que acontece |
|---|---|
| abaixo de 0,551 | negativa fora do documento passa pelo corte. Inaceitável: é o caso em que o sistema conversa sobre bolo de cenoura com base num PDF de lei |
| **0,551 a 0,644** | **todas as negativas fora do documento recusadas, nenhuma falsa recusa** |
| de 0,674 para cima | as seis negativas são recusadas, mas a C01 (0,669) cai junto — falsa recusa |

`0,605` fica praticamente no meio de `[0,551; 0,644]`, com ~0,054 de folga para
cada lado. Não é o valor que maximiza a recusa; é o que maximiza a **distância
até o erro mais próximo em qualquer direção**, que é outra coisa e é a que
importa quando a próxima pergunta não está no dataset.

### A sobreposição que nenhum limiar resolve

Este é o resultado que mais diz sobre o sistema, e ele não é bonito:

- maior similaridade entre as **negativas**: **0,668** (sanções administrativas)
- menor similaridade entre as **positivas**: **0,669** (C01, a continuação)
- folga: **0,001**

Um milésimo. As três negativas de mesmo vocabulário — sanções, incidente de
segurança, decisão automatizada — pontuam entre 0,644 e 0,668, coladas na
positiva mais fraca. **Nenhum valor de limiar separa as duas famílias.** Subir o
corte até pegar as três custa recusar uma pergunta que o documento responde, e
falsa recusa é o pior erro deste produto (BUG-002).

A razão é simples quando se olha o texto: "quais são as sanções administrativas
aplicáveis por infração a esta Lei?" compartilha quase todo o vocabulário do
documento — *Lei*, *infração*, *aplicável*, *administrativa*. A distância de
cosseno mede assunto, e o assunto **é** o mesmo. O que difere é se a resposta
está lá, e isso o vetor não sabe.

**Por isso a recusa tem duas camadas, e o gate só cobra a primeira:**

| camada | o que ela pega | como se verifica |
|---|---|---|
| limiar de similaridade | pergunta de outro assunto | `make eval` — 3/3, sem custo de geração |
| instrução de fundamentação no prompt | pergunta do mesmo assunto cuja resposta não está nos trechos | teste ponta a ponta contra a API real |

A segunda camada foi verificada contra o stack real, com as três negativas que
passam pelo limiar. As três foram recusadas:

```
P: Quais são as sanções administrativas aplicáveis por infração a esta Lei?
R: Não encontrei nos trechos fornecidos a lista ou a descrição das sanções
   administrativas aplicáveis por infração a esta Lei. […]

P: Em quanto tempo o controlador deve comunicar um incidente de segurança
   à autoridade nacional?
R: Não encontrei a informação sobre o prazo para a comunicação de incidentes
   de segurança à autoridade nacional nos trechos fornecidos.

P: O titular pode solicitar a revisão de decisões tomadas exclusivamente de
   forma automatizada?
R: Não encontrei a informação sobre a possibilidade de o titular solicitar a
   revisão de decisões tomadas exclusivamente de forma automatizada nos
   trechos fornecidos.
```

Recusa ponta a ponta: **6 de 6**. O `make eval` mede 3 de 6 porque mede só a
primeira camada — e é assim que deve ser, porque é a única que ele pode medir
sem gastar geração em toda rodada.

### Limitações honestas destes números

- **A amostra é pequena**: 19 positivas e 6 negativas. `recall@1 = 1,000` não é
  "retrieval perfeito"; é "nenhuma das 19 falhou". Uma falha custaria 0,053.
- **`MRR = 1,000` significa que as 19 acertaram em primeiro lugar.** É o teto da
  métrica, e um teto atingido é um sinal de que a métrica parou de discriminar
  neste dataset — não de que o problema acabou. Perguntas mais ambíguas
  derrubariam o número, e é isso que uma próxima rodada deveria buscar.
- **A folga de 0,001 é desta combinação** de documento, dataset e modelo. Um
  documento com capítulos sobre assuntos vizinhos comprime ainda mais. O limiar
  precisa ser **remedido** a cada troca de documento de referência, nunca
  herdado — foi exatamente o que aconteceu aqui: o 0,561 do documento anterior
  não sobreviveu à troca.
- **A condensação medida é o fallback determinístico** (`should_condense` +
  `fallback_query`), não a reescrita por LLM: é o caminho sem quota e sem
  variância entre rodadas. A reescrita do modelo só pode ser melhor que
  concatenar as duas perguntas, então C01–C03 medem um **piso**.
- **As três continuações provam o ponto**: C01 e C03 sobem da 2ª para a 1ª
  posição quando condensadas; a C02 já acertava crua, porque "crianças" é termo
  suficiente sozinho.
- **A quota do free tier limita a cadência.** O modelo de embeddings aceita 100
  requisições por minuto: a ingestão de 91 chunks mais as 25 consultas do eval
  estouram a janela se rodarem coladas. Não afeta os números, afeta quem for
  reproduzir.

---

## Medições anteriores

As rodadas de `A.5`, `A.7` e do BUG-002 foram feitas contra um documento
institucional de três páginas que **não está mais neste repositório** — era
material de um cliente, e saiu quando o projeto foi aberto. As tabelas daquelas
rodadas saíram junto: números sobre um documento que ninguém pode abrir não são
verificáveis, e número não verificável em documento de engenharia é decoração.

O que aquelas rodadas ensinaram, e continua valendo:

- **`A.5` — o limiar tem de sair de medição, não de intuição.** A calibração
  contra chunks reais deu 0,625 num documento onde a folga entre positivas e
  negativas era de 0,198. Aqui, com outro documento, a folga virou 0,001 e o
  limiar virou 0,605. O método sobreviveu; o número, não — que é precisamente o
  ponto.
- **`A.7` — a busca densa borra termo exato.** No dataset de então o delta da
  fusão RRF foi **zero**, nas seis métricas. Em consulta por termo literal, que
  aquele dataset não continha, a diferença apareceu inteira: um endereço de
  e-mail que não aparecia no top-3 denso subiu para a 2ª posição com a fusão. O
  motivo é do Postgres: `to_tsvector('portuguese', …)` trata um e-mail como
  **um token atômico**, então a via lexical casa o token exato que o vetor
  dilui entre trechos do mesmo assunto. As duas coisas eram resultado, e as duas
  estão registradas — inclusive a de delta zero.
- **BUG-002 — pergunta sem âncora tem outro piso.** Num documento institucional o
  nome da empresa aparece em quase todo chunk e funciona como âncora: perguntas
  que o repetiam pontuavam alto, e o limiar calibrado só com elas recusava as
  perguntas em linguagem corrente. O dataset ganhou positivas sem âncora, e o
  limiar caiu. Aqui a mesma divisão está no dataset (P11–P16 não citam o número
  do artigo), pelo mesmo motivo.
