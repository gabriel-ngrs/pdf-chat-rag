---
id: BUG-001
titulo: "Pergunta de continuação com 4 palavras não é condensada e vira recusa falsa"
descoberto_em: 2026-08-17
descoberto_por: teste de ponta a ponta do owner (bloco 3 do roteiro)
severidade: alta
fase_dona: A.2 (core-prompting)
status: aberto
---

# BUG-001 — Continuação de 4 palavras não condensa

## Sintoma

Na interface, a sequência:

1. `Quem fundou a YAITEC?` → responde certo, cita a página 2
2. `e a formação dele?` → **"Não encontrei essa informação no documento enviado"**

O documento diz, na página 2: *"Ygor Alves, fundador e CEO, engenheiro eletricista
pela UFPB"*. A resposta existe e o sistema recusou.

O owner relatou "às vezes funciona, outras não" — a diferença é o número de
palavras da pergunta, não o acaso.

## Causa raiz

Duas condições se somam em `backend/app/core/condensation.py`:

**1. O limiar é `< 4` e a pergunta tem exatamente 4 palavras.**

```
'e a formação dele?'    -> condensa? False   (4 palavras)   <-- o bug
'e a formação?'         -> condensa? True    (3 palavras)
'e quanto a isso?'      -> condensa? True    (4 palavras, mas tem marcador)
```

`SELF_CONTAINED_MIN_WORDS = 4` e o teste é `len(palavras) < 4`. Uma pergunta de
exatamente 4 palavras cai fora.

**2. `dele` não é marcador anafórico.**

A lista de `ANAPHORIC_MARKERS` tem `ele` e `ela`, mas o casamento é com fronteira
de palavra (`\bele\b`), e em `dele` não há fronteira entre `d` e `e`. As formas
contraídas — `dele, dela, nele, nela, disso, nisso` — são as mais comuns em
português falado e **nenhuma** está na lista.

Sem condensar, `"e a formação dele?"` vai crua ao retrieval. O embedding de uma
frase sem conteúdo semântico não alcança nenhum chunk acima do limiar, e o turno
recusa. Medido no log: `top_score = 0.527`, contra o limiar de `0.625`.

## Por que passou pelos testes

`tests/test_condensation.py` cobre os três casos do AC-3 e mais quatro, mas todos
com 2, 3 ou 5+ palavras. **A fronteira exata (4 palavras) não é testada**, e
nenhum caso usa forma contraída.

Vale registrar a origem: o limiar 4 nasceu na `A.2` para satisfazer o AC-3, que
exige que `"qual o endereço da empresa?"` (5 palavras) **não** condense. A
avaliação da fase aprovou a escolha e a spec foi corrigida de `< 12` para `< 4`.
O que ninguém viu é que 4 é apertado demais pelo outro lado.

## Correção sugerida

Duas mudanças pequenas, ambas em `condensation.py`:

1. **Acrescentar as formas contraídas** a `ANAPHORIC_MARKERS`: `dele, dela,
   deles, delas, nele, nela, disso, nisso, dessa, desse`. É a correção que
   resolve o caso relatado sem mexer no limiar.
2. **Reavaliar o limiar de palavras.** Com os marcadores contraídos na lista, o
   ramo do tamanho passa a ser rede de segurança, e não o mecanismo principal.
   Se subir para `< 6`, conferir que o AC-3 continua valendo (a pergunta do AC
   tem 5 palavras — `< 6` a condensaria, então **não** suba além de 5).

Acrescentar teste da fronteira exata (3, 4 e 5 palavras) e de pelo menos duas
formas contraídas.

## Encaminhamento

Rework da fase `A.2`, que é dona de `core/condensation.py` e de
`tests/test_condensation.py`. **Não** consertar dentro da `B.5`.
