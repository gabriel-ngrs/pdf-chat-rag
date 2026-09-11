---
id: BUG-006
titulo: "Conversa mais alta que a janela para de rolar por dentro e empurra o campo de pergunta para fora da tela"
descoberto_em: 2026-08-18
descoberto_por: segunda rodada do roteiro de ponta a ponta, automatizada com Playwright (bloco 9)
severidade: alta
fase_dona: B.1 (design-system, dona do `AppShell`) — regressão introduzida em `df3ac95`
status: corrigido e verificado (/double-check 2026-08-18)
---

# BUG-006 — A conversa longa rola a página inteira, não a lista

## Sintoma

A partir do momento em que a conversa fica mais alta que a viewport, a área de
conversa **para de rolar por dentro** e quem passa a rolar é a página. Medido
com 22 mensagens numa janela de 1440×900:

```
viewport da conversa   scrollHeight 4059 = clientHeight 4059   não transborda
página                 scrollHeight 4356 vs clientHeight 900   rola a página
campo de pergunta      y = 3823                                fora da tela
```

Três efeitos, e os três aparecem em qualquer demonstração que passe de ~8
mensagens:

1. **A conversa abre no topo, na primeira pergunta**, e não na última resposta.
   Quem recarrega a página com histórico cai no começo da conversa.
2. **O acompanhamento do fim fica inerte.** `useStickToBottom`
   (`MessageList.tsx:66`) escreve `viewport.scrollTop = viewport.scrollHeight`
   num elemento que não tem transbordo — a atribuição é aceita e não faz nada.
   Mandar uma pergunta nova não traz a resposta para a vista.
3. **O campo de pergunta sai da tela.** É preciso rolar a página inteira para
   perguntar de novo — exatamente o que o comentário do `ChatView` diz que a
   altura fixa existe para evitar:

   > A altura é fixada em relação à viewport para o campo de pergunta ficar
   > sempre visível: numa conversa longa, um rodapé que desce com a página
   > obrigaria a rolar até o fim para perguntar de novo.

Com conversa curta nada disso aparece: enquanto o conteúdo cabe na linha do
grid, o `ScrollArea` se comporta. Por isso passou por dois testes de ponta a
ponta — o do owner e o primeiro lote automatizado — sem ser visto.

## Causa raiz

`AppShell.tsx:138` monta a casca como

```tsx
<div className="grid min-h-dvh grid-rows-[auto_1fr_auto]">
```

`min-h-dvh` é **altura mínima**, não altura. A linha `1fr` fica livre para
crescer além da viewport quando o conteúdo pede, e cresce. O `h-full` do
`ChatView` (`ChatView.tsx:196`) resolve para essa altura crescida, o
`ScrollArea` recebe 4059 px de altura, e um elemento com a altura do próprio
conteúdo nunca transborda.

O `min-h-0` que a `<main>` carrega (`AppShell.tsx:156`) resolve o problema
oposto — deixa o conteúdo **encolher** dentro da linha. Não dá altura definida a
ela.

### É regressão, e dá para datar

Até `df3ac95` o `ChatView` tinha altura própria:

```diff
- <div className="flex h-[calc(100dvh-14rem)] min-h-96 flex-col gap-4">
+ <div className="flex h-full min-h-96 flex-col gap-4">
```

O `calc(100dvh - 14rem)` era um número medido à mão — cabeçalho + respiro do
`main` + rodapé — e o commit o trocou por `h-full` com uma justificativa
correta: aquele 14rem descolava sozinho quando o respiro do `main` mudasse.

O que a troca não viu é que `h-full` **exige** que o pai tenha altura definida,
e o pai nunca teve. A falha estava latente no `min-h-dvh` desde
`655c44f` (a fase B.1, que criou a casca); o `calc` a escondia porque não
dependia do pai. Trocar o `calc` por `h-full` sem trocar `min-h-dvh` por altura
definida acendeu a falha.

## Reprodução

1. `docker compose up --build`, subir o `documento-de-exemplo.pdf`.
2. Fazer 10 perguntas na mesma conversa, numa janela de 900 px de altura.
3. Observar: a página inteira ganhou barra de rolagem, e o campo de pergunta
   não está mais visível.
4. `F5`. A conversa reabre na primeira pergunta.

Verificação de que é a altura, e não o `ScrollArea`, forçando no console com a
conversa carregada:

```js
document.querySelector('div.grid.min-h-dvh').style.height = '100dvh'
```

Depois disso: `clientHeight` do viewport volta a 603, a página volta a 900, o
campo volta a ficar visível e a rolagem interna volta a funcionar. Uma linha, e
os três efeitos somem juntos.

## Correção sugerida

Dar altura definida à casca, mantendo o `min-h` como piso para o caso do
conteúdo curto:

```diff
- <div className="grid min-h-dvh grid-rows-[auto_1fr_auto]">
+ <div className="grid h-dvh grid-rows-[auto_1fr_auto]">
```

`h-dvh` puro é o que restaura o comportamento e é o que foi verificado ao vivo.
Se alguma tela precisar crescer além da viewport (a de entrada não precisa — foi
justamente o que `df3ac95` garantiu), a alternativa é `min-h-dvh` **com**
`grid-rows-[auto_minmax(0,1fr)_auto]`, que impede a linha do meio de crescer
sem travar a casca inteira.

Não mexer no `ChatView`: o `h-full` está certo, e é o pai que estava mentindo
sobre a altura.

## Teste de regressão

O `MessageList.test.tsx` não alcança isto — o jsdom não calcula altura, e o
próprio projeto já registra essa limitação ao extrair `isNearBottom` como função
pura testável. A prova precisa de navegador de verdade: montar a conversa até
passar da viewport e asserir que

- `viewport.scrollHeight > viewport.clientHeight`, e
- `document.documentElement.scrollHeight <= clientHeight + 2`, e
- o `<form>` do campo de pergunta tem `getBoundingClientRect().bottom <= innerHeight`.

## Encaminhamento

`/bugfix`. Fase dona da casca é a `B.1` (design-system) da `01-ingestao-pdf`,
mas a regressão entrou por um commit de UI fora do fluxo de fases (`df3ac95`) —
vale registrar isso na decisão, porque é o segundo defeito de layout que nasce
de mudança direta no `AppShell` sem passar por avaliação de fase.

É o mais grave dos cinco desta rodada: não exige entrada estranha nem falha de
rede, só uma conversa de tamanho normal.
