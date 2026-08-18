---
id: BUG-009
titulo: "A condensação estoura os 5 s de timeout e custa 5 segundos parados numa pergunta de uma palavra"
descoberto_em: 2026-08-18
descoberto_por: segunda rodada do roteiro de ponta a ponta, automatizada com Playwright (bloco 5)
severidade: baixa
fase_dona: A.2 (core-prompting, dona de `core/condensation.py`)
status: aberto
---

# BUG-009 — Cinco segundos de silêncio antes de uma resposta de uma linha

## Sintoma

Na pergunta `StartStak` — nove caracteres, um termo solto — o turno levou
**8,9 s**, dos quais 5 foram a condensação esperando o timeout inteiro antes de
desistir:

```json
{"conversation_id":"e827ce47…","used_llm":false,"fallback":true,
 "duration_ms":5001,"event":"chat.condensed"}
{"candidates":5,"above_threshold":5,"top_score":0.646,"duration_ms":514,"event":"chat.retrieved"}
{"token_count":3,"truncated":false,"duration_ms":8862,"event":"chat.generated"}
```

`5001 ms` contra `CONDENSE_TIMEOUT_SECONDS=5` não é coincidência: é o timeout
cheio. O fallback fez o certo — seguiu com a pergunta crua, o retrieval
recuperou os trechos da página 2 e a resposta saiu correta. O custo foi só
tempo, e todo ele antes do primeiro token, que é onde tempo mais dói.

Para calibrar: nas outras 44 perguntas da rodada a condensação respondeu em
**813 ms** e **967 ms**. Esta foi a única a estourar, o que sugere latência do
provedor e não regra do código.

## Causa raiz

Não há erro de lógica. O desenho é: condensar com o LLM, e se demorar demais,
cair para a pergunta crua. O que o desenho não faz é **evitar a chamada quando
ela não tem trabalho a fazer**.

`StartStak` é um termo autocontido. Não há pronome, não há elipse, não há nada
que a condensação pudesse resolver — a pergunta crua e a condensada seriam a
mesma string. A chamada foi paga (e neste caso paga em dobro: 5 s de espera e
uma requisição gasta da cota) para produzir o que já estava em mãos.

Vale lembrar que o [BUG-001](001-condensacao-nao-dispara-em-pergunta-de-4-palavras.md)
foi exatamente o oposto: uma heurística que **deixava de condensar** perguntas
curtas, e uma continuação de quatro palavras virava recusa falsa. A correção
daquele bug foi passar a condensar sempre que houver histórico — que é o
comportamento certo, e é o que produz este custo aqui.

Ou seja: os dois defeitos são as duas bordas da mesma decisão, e qualquer
mudança aqui precisa **não** reabrir o 001.

## Reprodução

Não é determinística — depende da latência do provedor. O que dá para observar
sempre é a condição que a torna possível:

1. Fazer uma pergunta qualquer (para haver histórico).
2. Perguntar um termo autocontido: `StartStak`, `UFPB`, `contato@yaitec.com`.
3. `docker compose logs backend | grep chat.condensed` — o evento aparece com
   `used_llm: true` em toda pergunta a partir da segunda, inclusive nas que não
   têm o que condensar.

## Correção sugerida

O caminho seguro **não** é uma heurística de tamanho — foi ela que produziu o
BUG-001. É reduzir o custo do caso ruim sem mexer em quando condensar:

1. **Baixar `CONDENSE_TIMEOUT_SECONDS` de 5 para 2.** As duas condensações bem
   sucedidas da rodada fecharam em menos de 1 s; 2 s dá folga de 2× sobre o
   observado e corta o pior caso pela metade. É uma linha de `.env`, e o
   fallback já existe e funciona.
2. **Emitir o "pensando" com texto diferente durante a condensação.** Hoje a
   tela diz "Juntando os trechos…" desde o Enter, o que é falso enquanto a
   condensação roda — ninguém está juntando trecho nenhum ainda. Não deixa o
   turno mais rápido, mas deixa de mentir sobre o que está acontecendo.

Se alguém quiser mesmo pular a chamada, o critério tem de ser **ausência de
dependência do histórico**, não tamanho — e isso é caro de decidir sem o
modelo. Registro como caminho descartado, para o próximo que pensar nele
encontrar o BUG-001 pelo caminho.

## Encaminhamento

Rework da `A.2` só se for o caminho 2. O caminho 1 é configuração e decisão do
owner. Baixa prioridade: aconteceu uma vez em 45 perguntas, e o fallback
protegeu a resposta.
