---
versão: 1.0
status: estável
atualizado: 2026-08-18
data: 2026-08-18
workflow: melhorias
tags: [ui, design-system, motion, acessibilidade, dependencias, entrega]
status_decisão: ativa
supersede: null
relaciona-com: [MELH-001, MELH-002, MELH-003, MELH-004]
---

# Decisões: paleta da Yaitec, fundos das telas e o limite do movimento

## Contexto

As quatro melhorias abertas depois do teste de ponta a ponta chegaram com três
perguntas que o documento não podia responder sozinho, e que a
[`MELH-002`](../melhorias/002-background-animado-e-paleta-escura.md) listava
explicitamente como decisão do owner. As respostas vieram na abertura do
trabalho e estão registradas aqui, junto com as escolhas que decorreram delas.

Duas restrições atravessam tudo o que segue e não foram afrouxadas em nenhum
ponto: cor sempre por token semântico, e `prefers-reduced-motion` respeitado
inclusive onde a regra de CSS não alcança.

## Decisões tomadas

### 1. A paleta é a do site da yaitec.com, traduzida para os tokens que já existem

**O que o owner respondeu:** "quero manter a paleta do site da yaitec.com".

**O que isso virou:** o CSS do site foi lido e a paleta extraída — `#7BA6D1`
(azul-aço das ações), `#12191F` e `#1D2730` (as duas superfícies escuras),
`#9BBFDF` e `#AACDF2` (as diluições do azul), `#FBF9F8` (papel quente). Todos
foram convertidos para `oklch` e escritos nos tokens que o `index.css` já
declarava, sem criar token novo e sem renomear nenhum.

Três consequências que valem registro:

- **O âmbar saiu.** O marca-texto era `oklch(0.86 0.13 84)` e passou a ser a
  diluição clara do azul da marca. Ele continua fazendo o mesmo trabalho —
  marcar a citação, marcar a seleção de texto, marcar o "Doc" do wordmark —, só
  que agora na cor de quem assina o produto.
- **A ação virou azul.** O `--primary` era tinta; passou a ser o `#7BA6D1`, que
  é o azul dos botões do site. O texto sobre ele é tinta, e não branco: branco
  dá 2,6:1 e reprovaria o gate de contraste.
- **O fundo escuro ficou abaixo da marca.** O pedido original era "paleta mais
  escura", e o escuro mais escuro do site é `#12191F` (L 0.209) — mais claro
  que o `oklch(0.17)` que o projeto já tinha. A rampa resolveu os dois: o fundo
  desce para `oklch(0.16)`, o card é o `#12191F` e o elevado é o `#1D2730`.
  Mais escuro que antes, e literalmente as superfícies do site.

Todos os pares de texto foram medidos antes de entrar: o pior deles é 6,9:1, e
o anel de foco, que é traço fino e responde ao mínimo de 3:1, ficou em 4,4:1.

**Também decidido:** o tema escuro passou a ser o padrão, no `ThemeProvider` e
no script anti-piscada do `index.html` — os dois juntos, porque discordarem é o
piscar que aquele script existe para evitar.

### 2. Os fundos: ondas na entrada, malha estática na conversa

**O que o owner respondeu:** `GradientWaves` na tela de upload, e na tela de
chat o `ShapeGrid`, "porém estático".

**O que isso virou:** dois componentes portados para TypeScript strict, com o
código de referência guardado como veio em
[`anexos/002-gradient-waves/`](../melhorias/anexos/002-gradient-waves/).

O `ShapeGrid` estático é uma simplificação grande, e é a decisão certa duas
vezes. A referência faz a malha derivar na diagonal a 60 fps e acende a célula
sob o ponteiro; esse fundo fica atrás da conversa, que é o texto que a pessoa
está lendo com atenção. Sem laço, some o custo de GPU durante toda a leitura e
some a pergunta sobre movimento reduzido — não há movimento a reduzir. O que
saiu junto: `requestAnimationFrame`, `IntersectionObserver`,
`visibilitychange`, rastro de hover e opacidades por célula, tudo existia para
servir a um laço que não existe mais.

### 3. O fundo mora onde o texto não mora

O critério de aceite mais duro da `MELH-002` é que nenhum texto fique
diretamente sobre o shader: o fundo muda de cor a cada frame, e contraste
medido uma vez ali não vale para o frame seguinte.

**Decisão:** em vez de auditar cada pedaço de texto atrás de uma superfície, os
dois fundos são recortados por uma máscara radial de `46rem` — quatro rem além
da coluna de leitura de `42rem`. O fundo é apagado na faixa onde o texto vive e
aparece emoldurando-a pelas margens.

**Por quê:** a alternativa era dar superfície a cada elemento solto, e ela
falhava no caso concreto — o rótulo "COMO FUNCIONA" da tela de envio não tem
card e não deveria ganhar um só por causa do fundo. A máscara resolve a classe
inteira do problema em vez de um caso, e continua valendo para qualquer texto
que a tela ganhe depois. Em tela estreita a elipse cobre a viewport e o fundo
some — que é o certo, porque ali não há margem onde ele coubesse.

A abertura da tela de envio ganhou superfície própria pelo mesmo motivo, e ela
é opaca: 90% com desfoque deixaria 10% de um campo que muda passando por baixo
do maior texto da página.

**Consequência medida:** o `fogDepth` do shader subiu de 15 para 45. Na sintonia
original a névoa era roxo vivo e dominava a tela; aqui ela é o fundo da página,
então com 15 o campo inteiro se dissolvia no fundo e o efeito era invisível.

### 4. A logo entrou vetorizada, não como o arquivo entregue

**O que o owner respondeu:** "coloquei na raiz do projeto" — o `Svg Yaitec.svg`.

**O problema:** o arquivo tem 538 kB e não é vetor. É um PNG de 1440 px
embrulhado em SVG, sobre um retângulo navy chapado. Servido como está, seria
meio megabyte no cabeçalho e um quadrado escuro no tema claro.

**Decisão:** o desenho foi vetorizado a partir daquele arquivo — contornos
traçados e simplificados a três formas fechadas, 1 kB — e entrou como
componente React pintado com `currentColor`. Atravessa os dois temas sem dois
arquivos e serve também de favicon, que o projeto não tinha. O arquivo original
está preservado em
[`anexos/003-logo/`](../melhorias/anexos/003-logo/svg-yaitec-original.svg).

**Alternativa rejeitada:** máscara CSS sobre o PNG recortado. Resolveria o tema,
mas manteria o peso e a borda serrilhada em telas de alta densidade.

### 5. Markdown renderizado no cliente, com o prompt como complemento

A `MELH-001` oferecia dois caminhos e recomendava os dois juntos. Foi o que se
fez, com a divisão de responsabilidade explícita: **quem garante que nenhum
asterisco aparece na tela é o renderizador**, e a instrução no prompt só
estreita a variedade que ele precisa cobrir. Instrução se obedece na maioria
das vezes; renderizador não tem maioria.

Três escolhas dentro disso:

- **HTML do documento vira texto literal, nunca elemento.** Sem `rehype-raw` o
  `react-markdown` já não executa nada, mas ele **descarta** as marcas — uma
  resposta que dissesse "use a tag `<script>`" apareceria mutilada. Um plugin de
  seis linhas troca o tipo do nó de `html` para `text`, e o teste que prova isso
  é o que impede a melhoria de virar um XSS.
- **Durante o stream o texto é cru.** Markdown em construção é Markdown inválido
  na maior parte do tempo, e reprocessar a string a cada token faria o parágrafo
  refluir a cada frame — numa lista que mede `scrollHeight` para se manter no
  fim.
- **`img` fica de fora.** Uma imagem numa resposta seria o navegador buscando
  uma URL escolhida por quem escreveu o PDF.

### 6. O movimento tem dois degraus, e nenhuma biblioteca nova

A `MELH-004` pedia animações de mouse, de cards e de textos. O que entrou:
`--animate-rise` para conteúdo que acabou de chegar e `--animate-fade` para
troca de conteúdo no mesmo lugar. Dois, pelo mesmo motivo de haver quatro
degraus de texto — um terceiro seria escolha sem critério.

**O que ficou de fora, e por quê:** animação por caractere ou por palavra na
resposta (o streaming **já é** a animação do texto), efeito de máquina de
escrever (atrasaria texto que já está pronto), cursor customizado (quebra
affordance), e `framer-motion` (~40 kB e um segundo sistema de animação
convivendo com o `tw-animate-css` que já está instalado).

**A parte que exige cuidado:** a regra de movimento reduzido do `index.css` é
CSS, e não alcança um `requestAnimationFrame`, um listener de `pointermove` nem
a decisão de aplicar uma classe. Por isso tudo que se move por JS passa por um
hook que lê a media query, e a decisão é **não existir** em vez de existir com
duração zero — o que torna cada uma verificável por teste, que era o critério
de aceite. O reset ganhou também `animation-delay`: numa entrada escalonada,
zerar só a duração deixaria o último item invisível pelo tempo do atraso.

### 7. Duas dependências novas

`react-markdown` + `remark-gfm` (a `MELH-001` não tem como ser feita sem
renderizador) e `ogl` (única dependência de runtime do `GradientWaves`).
`npm audit --audit-level=high` limpo. O `ShapeGrid` e todas as animações da
`MELH-004` saíram sem dependência nenhuma.

**Custo assumido:** o bundle foi de ~350 kB para 616 kB minificado (191 kB
gzip). Não foi feito code-splitting porque o fundo animado está na primeira
tela — adiá-lo não adiantaria o que ele adia.

## Verificação

`make check` verde (278 testes de backend, 111 de frontend) e
`npm audit --audit-level=high` limpo. Os dois fundos, os dois temas e a resposta
em Markdown foram conferidos em navegador de verdade; a ausência dos rótulos de
leitor de tela na cópia foi verificada selecionando a conversa inteira e lendo
o resultado da seleção, que é o que o `Ctrl+C` leva.
