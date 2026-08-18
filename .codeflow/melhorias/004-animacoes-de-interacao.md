---
id: MELH-004
titulo: "Animações de mouse, cards e textos"
solicitado_em: 2026-08-17
solicitado_por: owner
tipo: motion / micro-interação
area: frontend
prioridade: média
esforco: médio
status: aberto
fase_dona: B.1 (design-system), B.2 (app-shell), B.3 (chat-view)
---

# MELH-004 — Movimento na interface: mouse, cards e texto

## O pedido

Colocar animações de mouse, de cards e de textos.

## O que existe hoje

Quase nada, e por escolha registrada. O `index.css` diz, na seção do design
system:

> Profundidade por hierarquia (peso, tamanho, espaço, 1px de borda), não por
> sombra. Há exatamente uma sombra no sistema, e ela é para elemento flutuante.

O que já se move:

- transições de estado dos componentes shadcn (hover e foco de botão, abertura
  de dialog, toast do `sonner`);
- `tw-animate-css` está instalado e é o que anima os componentes do Radix;
- os `Skeleton` do estado "pensando" pulsam;
- a barra de progresso do upload avança.

O que **não** se move: entrada de mensagem na conversa, entrada dos chips de
citação, os cards, o dropzone além do hover básico, e qualquer coisa ligada à
posição do ponteiro.

## Onde o movimento paga o custo

Movimento em produto de leitura tem uma régua: ele serve para explicar o que
acabou de acontecer, não para decorar. Priorizado por essa régua:

### 1. Entrada da resposta e dos chips (o que mais rende)

Quando o stream termina, os chips de citação aparecem de uma vez, sem aviso.
Uma entrada escalonada (fade + 4 px de subida, ~20 ms de defasagem entre chips)
diz "estes vieram junto com aquela resposta". É o movimento com maior retorno
porque explica uma relação real.

### 2. Cards e dropzone

- `UploadDropzone` — o estado de arrasto merece resposta imediata: borda que
  acende, escala mínima (`1.01`, não mais), transição de 120 ms;
- `ProcessingStatus` — a passagem entre etapas do processamento é hoje uma troca
  seca de texto. Um crossfade curto mostra que houve progresso, não recarga;
- cards em geral: hover com elevação por **borda e superfície**, não por sombra
  nova — o sistema tem uma sombra só, e ela é de elemento flutuante.

### 3. Texto

Aqui é onde é mais fácil errar. Animar a entrada de cada linha de uma resposta
que já chega token a token é animar duas vezes a mesma coisa: o streaming **já
é** a animação do texto. O que cabe:

- o título da tela inicial e o texto de estado vazio entram com fade curto;
- a resposta **não** ganha animação por caractere ou por palavra;
- nada de efeito de máquina de escrever — ele atrasaria texto que já está pronto.

### 4. Mouse

O pedido de "animações de mouse" pode significar coisas bem diferentes:

| Leitura | Cabe aqui? |
|---|---|
| hover mais expressivo em elementos clicáveis | sim — é o que falta |
| brilho/spotlight que segue o ponteiro dentro do card | sim, com moderação |
| parallax do fundo animado | é a [MELH-002](002-background-animado-e-paleta-escura.md), não esta |
| cursor customizado substituindo o do sistema | não — quebra affordance e acessibilidade |

**Recomendação:** hover expressivo em tudo que é clicável, e no máximo um efeito
de spotlight seguindo o ponteiro no card da tela de upload. Efeito de ponteiro
dentro da conversa é ruído sobre o texto que a pessoa está lendo.

## Restrições que valem aqui

**`prefers-reduced-motion` já é garantia do projeto.** O `index.css` zera
duração de animação e de transição para quem pede movimento reduzido. Isso
cobre CSS — e é mais uma razão para preferir CSS a JS neste trabalho. Qualquer
animação em JS (`requestAnimationFrame`, biblioteca de motion) precisa checar a
media query por conta própria.

**Sem biblioteca nova, se possível.** `tw-animate-css` + transições do Tailwind
cobrem tudo que está listado acima. `framer-motion` traria ~40 kB e um segundo
sistema de animação convivendo com o primeiro — só justificável se o escalonamento
de listas ficar impraticável em CSS puro, o que não parece ser o caso.

**Animar só `transform` e `opacity`.** São as duas propriedades que o compositor
resolve sem relayout. Animar `height`, `top` ou `width` numa lista que já rola e
recebe token a token é caminho conhecido para engasgo.

**A conversa rola sozinha.** `MessageList` tem `useStickToBottom`, que mede
`scrollHeight` para decidir se acompanha o fim. Animação que muda a altura do
conteúdo durante o stream interfere nessa medida — mais um motivo para o
movimento ficar em `transform`/`opacity`, que não alteram o layout.

**Duração.** Micro-interação entre 120 ms e 200 ms; entrada de conteúdo até
250 ms. Acima disso a interface parece lenta em vez de fluida.

## Critérios de aceite

- [ ] Com `prefers-reduced-motion: reduce`, nenhuma das animações novas roda —
      verificado por teste, não só por inspeção.
- [ ] Nenhuma animação nova usa propriedade que causa relayout.
- [ ] O acompanhamento de scroll da conversa continua correto durante o stream
      (testes de `MessageList.test.tsx` verdes).
- [ ] Nenhuma dependência nova de animação, ou justificativa registrada em
      `.codeflow/decisions/` se houver.
- [ ] Nenhum cursor customizado.
- [ ] `make check` verde.
