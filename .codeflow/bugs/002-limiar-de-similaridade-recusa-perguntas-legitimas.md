---
id: BUG-002
titulo: "SIMILARITY_THRESHOLD=0,625 recusa perguntas legítimas; a calibração não representa o uso real"
descoberto_em: 2026-08-17
descoberto_por: teste de ponta a ponta do owner (blocos 3 e 5 do roteiro)
severidade: alta
fase_dona: A.5 (rag-eval)
status: corrigido e verificado (/double-check 2026-08-18)
---

# BUG-002 — Recusa falsa em pergunta que o documento responde

## Sintoma

Perguntas legítimas, cuja resposta está no PDF, são recusadas:

| pergunta | resultado | resposta existe? |
|---|---|---|
| `Qual o e-mail de contato?` | **recusou** | sim, página 3 |
| `O que é a sigla citada no documento?` | **recusou** | sim, página 2 |

E as mesmas informações são entregues quando a pergunta muda de forma:

| pergunta | resultado |
|---|---|
| `contato@exemplo.com.br` | responde certo |
| `sigla do documento` | responde certo |

## Medição

Sete recusas no log desta sessão de teste, com o melhor score de cada turno:

```
top_score = 0.573   RECUSOU
top_score = 0.564   RECUSOU
top_score = 0.616   RECUSOU     <-- 0,009 abaixo do corte
top_score = 0.527   RECUSOU
top_score = 0.596   RECUSOU
top_score = 0.612   RECUSOU     <-- 0,013 abaixo do corte
top_score = 0.596   RECUSOU
                                    limiar = 0.625
```

Nos turnos que responderam, o `top_score` ficou entre `0.694` e `0.768`.

## Causa raiz

O limiar `0,625` foi calibrado na fase `A.5` como o ponto médio entre a negativa
mais alta (`0,526`) e a positiva mais baixa (`0,724`) do dataset. A folga de
`0,198` parecia confortável.

**O dataset não representa o uso real.** As 12 perguntas positivas mencionam
"o nome da empresa" explicitamente — `"Qual é o e-mail de contato da empresa?"`,
`"Quais são os valores da empresa?"`. O nome da empresa aparece em quase todos os
chunks de um documento institucional, e funciona como âncora que empurra a
similaridade para cima.

Quem usa escreve `"Qual o e-mail de contato?"`, sem a âncora. Aí a similaridade
cai para a faixa `0,53–0,62` — **exatamente a folga que o eval declarou vazia**.

A folga não é vazia; ela é ocupada pela forma como gente de verdade pergunta.

## Por que isto é grave

A recusa é o mecanismo que o desafio avalia com mais peso, e a falsa recusa é o
pior modo de falha: o sistema tem a informação, foi perguntado de forma clara, e
diz que não sabe. Numa demonstração, some com a credibilidade do produto.

Também vale notar: dois casos ficaram a **menos de 0,015** do corte. Não é
questão de reescrever a pergunta — é o corte estar no lugar errado.

## Correção sugerida

Não baixar o limiar às cegas: a recusa correta nas negativas é o contrapeso, e
derrubá-la seria trocar um defeito por outro. O caminho medido:

1. **Acrescentar ao `eval/dataset.json` perguntas positivas sem a âncora** —
   as mesmas informações, perguntadas como o owner perguntou (`"Qual o e-mail de
   contato?"`, `"O que é a sigla citada?"`). São elas que revelam o piso real.
2. **Remedir a distribuição** e recalibrar. Com as novas positivas, a positiva
   mais baixa deve cair para a casa dos `0,53`, e o ponto médio se move.
3. **Se a folga sumir** — negativas e positivas se sobrepondo —, aí a decisão é
   arquitetural, não de constante: o limiar sozinho não separa os dois grupos, e
   entra em cena reranking ou uma segunda condição para recusar.
4. Rodar `make eval` e registrar, como a `A.5` fez.

Este bug e o [BUG-001](001-condensacao-nao-dispara-em-pergunta-de-4-palavras.md)
se somam: a continuação não condensada chega ao retrieval como frase vazia
(`0,527`) e é recusada pelo mesmo corte.

## Encaminhamento

Rework da fase `A.5`, dona do dataset e da calibração. **Não** consertar dentro
da `B.5`, e **não** ajustar o limiar sem remedir — trocar a constante sem dado é
o que a `A.5` existe para não deixar acontecer.

---

**Corrigido em 2026-08-17** pelo lote `feat-0002-teste-ponta-a-ponta`
(`.codeflow/bug-batches/feat-0002-teste-ponta-a-ponta.md`). O fix, o teste de regressão e a reprodução manual estão na linha
deste bug no ledger; as escolhas não-triviais estão em
`.codeflow/decisions/2026-08-17-lote-de-bugs-do-teste-de-ponta-a-ponta.md`. O
`/double-check` rodou em **2026-08-18** e marcou este bug como **sanado (✓)**: o
teste de regressão falha contra o código pré-fix e a reprodução do relato foi
refeita. Detalhe na seção "Verificação" do ledger.
