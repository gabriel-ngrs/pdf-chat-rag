---
id: MELH-002
titulo: "Background animado (GradientWaves em WebGL) e paleta mais escura"
solicitado_em: 2026-08-17
solicitado_por: owner
tipo: identidade visual / motion
area: frontend
prioridade: média
esforco: alto
status: implementado
implementado_em: 2026-08-18
fase_dona: B.1 (design-system) e B.2 (app-shell)
anexos: anexos/002-gradient-waves/
---

# MELH-002 — Fundo animado e uma paleta mais escura

## O pedido

Colocar um background animado e adotar uma paleta mais escura. A referência
entregue é o `GradientWaves` (react-bits): um shader WebGL2 que faz raymarching
de um campo de ondas, com parallax de mouse, grão e névoa. O componente
completo, o CSS e o exemplo de uso do owner estão em
[`anexos/002-gradient-waves/`](anexos/002-gradient-waves/) — o código foi
guardado como veio, sem adaptação.

## Onde isso encosta no que já existe

O projeto **já tem** um tema escuro, e ele não é um dark mode genérico. O
`frontend/src/index.css` documenta a decisão em texto:

> metáfora → papel e tinta. O claro é papel quente; o escuro é tinta fria.
> O âmbar é o marca-texto — e é literalmente o que vai marcar a citação no chat.

O escuro atual é `oklch(0.17 0.012 265)` — quase preto, levemente azul. A
referência entregue é roxo `#5227FF` com cristas rosa `#FF9FFC`. São duas
identidades diferentes, e essa é a decisão que precisa sair antes do código.

## O que precisa ser decidido (owner)

### Decisão 1 — o que "mais escura" significa aqui

Três leituras possíveis, e elas levam a lugares distintos:

| Leitura | O que muda | Custo |
|---|---|---|
| **a. Escurecer o tema escuro atual** | baixar `--background` de `0.17` para ~`0.13`, aprofundar `--card`, recalibrar bordas | baixo — mexe em ~6 tokens |
| **b. Tornar o escuro o padrão** | inverter o default do `next-themes` e o script anti-flash do `index.html` | baixo |
| **c. Trocar a paleta pela do exemplo (roxo/rosa)** | abandonar "papel e tinta", refazer contraste de todos os estados, revalidar acessibilidade | alto — é rebranding |

**Recomendação:** (a) + (b). A metáfora papel/tinta é o que dá ao produto a cara
de ferramenta de leitura em vez de brinquedo de IA, e o âmbar do marca-texto é
funcional — ele marca a citação. Trocar por roxo/rosa custa a coerência inteira
por um efeito. Se o objetivo é impacto visual, ele vem do fundo animado, não da
troca de hue.

### Decisão 2 — as cores do shader

O `GradientWaves` recebe três cores. Elas podem ser derivadas dos tokens que já
existem em vez dos hex do exemplo:

- `horizonColor` → o `--background` escuro (a névoa dissolve o fundo no shader);
- `waveColor` → o azul frio da tinta, mais saturado;
- `crestColor` → o âmbar do marca-texto, que faz a crista brilhar na cor da marca.

Assim o fundo é animado **e** continua sendo este produto.

### Decisão 3 — onde o fundo aparece

Fundo animado atrás de uma conversa é fundo animado atrás de texto que a pessoa
está lendo com atenção. Opções, da mais segura à mais arriscada:

1. **Só na tela de upload** (antes de existir documento). É a tela de entrada, o
   texto é curto, e o efeito faz o trabalho de primeira impressão.
2. **Em toda a aplicação, com opacidade baixa e cobertura sólida na coluna de
   leitura.** Exige que o `AppShell` ganhe uma camada de fundo e que a área de
   mensagem tenha superfície própria.
3. **Atrás do chat, cheio.** Não recomendado: compete com o texto que é o
   produto.

**Recomendação:** (1) na entrega, com o componente já escrito de forma a
suportar (2) depois.

## O que o código de referência exige

Ele não entra como está. Levantamento honesto do que falta:

**Dependência nova.** `ogl` não está no `package.json`. É a única dependência
runtime do componente (~30 kB gzip). Passa por `npm audit --audit-level=high`,
que é gate do projeto.

**TypeScript strict.** O arquivo é `.jsx` sem tipos. `tsc --strict` sobre
`frontend/src` é regra da constitution — o componente precisa ser portado, com
tipos para as props e para os uniforms. Nada de `any`.

**`prefers-reduced-motion`.** O `index.css` já zera animação e transição para
quem pede movimento reduzido, mas essa regra **não alcança um `requestAnimationFrame`
em WebGL** — é CSS, e o shader não é CSS. O componente precisa ler a media query
em JS e, quando ela casar, renderizar **um único frame estático** em vez de
entrar no loop. Sem isso a melhoria quebra uma garantia de acessibilidade que o
projeto já dá hoje.

**Fallback sem WebGL2.** `new Renderer({ webgl: 2 })` falha em contexto sem
WebGL2 (navegador antigo, GPU bloqueada, aceleração desligada). Hoje isso
lançaria erro no `useEffect` e derrubaria a árvore. Precisa de `try/catch` e de
um fundo estático (gradiente CSS na mesma paleta) como degradação.

**Custo de bateria e de GPU.** O loop roda a 60 fps enquanto a aba está visível.
O componente de referência já faz duas coisas certas — para em
`visibilitychange` e em `IntersectionObserver`. Falta considerar `detail="low"`
em telas pequenas e limitar `dpr` (ele já limita a 2).

**Testes.** `vitest` roda em jsdom, que não tem WebGL. O componente precisa ser
testável sem contexto gráfico: teste do fallback, teste do caminho de movimento
reduzido, e mock de `ogl` no resto. Nenhum teste deve tentar compilar shader.

**Contraste.** Qualquer texto sobre o fundo animado precisa continuar em 4,5:1 —
e o fundo **muda de cor a cada frame**. A única forma segura é o texto nunca
ficar direto sobre o shader: ele fica sobre uma superfície (`--card`, ou o
`--background` com opacidade alta) que flutua acima.

## Critérios de aceite

- [x] Decisões 1, 2 e 3 registradas em `.codeflow/decisions/` antes do código.
- [x] Componente portado para TypeScript strict, sem `any`, `tsc` verde.
- [x] Com `prefers-reduced-motion: reduce`, nenhum frame além do primeiro é
      renderizado — verificado por teste.
- [x] Sem WebGL2, a página renderiza o fundo estático e nada quebra.
- [x] Nenhum texto da interface fica diretamente sobre o shader sem superfície
      intermediária; contraste medido nos dois temas.
- [x] O loop para quando a aba fica oculta (já vem no código de referência —
      confirmar que sobreviveu à port).
- [x] Cores do shader vêm de tokens, não de hex no componente (regra do
      `index.css`).
- [x] `make check` verde e `npm audit --audit-level=high` limpo.

## Resolução — 2026-08-18

As três decisões foram tomadas com o owner na abertura do trabalho e estão
consolidadas em
[`decisions/2026-08-18-paleta-e-fundos-das-telas.md`](../decisions/2026-08-18-paleta-e-fundos-das-telas.md).
O documento de decisões foi escrito no fechamento; as decisões precederam o
código, que era o que este critério protegia.

**Decisão 1 — paleta.** Nem (a), nem (b), nem (c) como estavam escritas: o owner
pediu a paleta do site da exemplo.com.br. Ela foi extraída do CSS do site
(`#7BA6D1`, `#12191F`, `#1D2730`, `#9BBFDF`, `#AACDF2`, `#FBF9F8`), convertida
para `oklch` e escrita nos tokens que já existiam — nenhum token novo, nenhum
renomeado. O efeito prático cobre o que (a) e (b) queriam: o fundo escuro desce
para `oklch(0.16)`, um degrau **abaixo** do `#12191F` da marca, e o escuro
virou o padrão. O âmbar do marca-texto deu lugar à diluição clara do azul da
marca, e continua fazendo o mesmo trabalho — marcar a citação, a seleção de
texto e o "Doc" do wordmark.

Todos os pares de texto foram medidos antes de entrar: o pior é 6,9:1, e o anel
de foco, que responde ao mínimo de 3:1 por ser traço fino, ficou em 4,4:1.

**Decisão 2 — cores do shader.** Como este documento propôs: névoa no
`--background`, corpo da onda no azul da marca, crista no marca-texto. Um teste
prende as cores vindo dos tokens, e não de hex no componente.

Consequência medida: o `fogDepth` subiu de 15 para 45. Na sintonia original a
névoa era roxo vivo e dominava a tela; sendo ela o fundo da página, com 15 o
campo inteiro se dissolvia no fundo e o efeito ficava invisível.

**Decisão 3 — onde o fundo aparece.** O owner escolheu as ondas na tela de
envio **e** uma segunda tela de fundo para o chat: o `ShapeGrid`, "porém
estático". As duas entraram.

O critério de "nenhum texto sobre o shader" foi resolvido por classe, não por
caso: os dois fundos são recortados por uma máscara radial de `46rem` — quatro
rem além da coluna de leitura —, e o fundo aparece emoldurando a coluna pelas
margens. A alternativa era dar superfície a cada elemento solto, e ela falhava
no caso concreto: o rótulo "COMO FUNCIONA" não tem card e não deveria ganhar um
só por causa do fundo. A abertura da tela de envio ganhou superfície própria, e
opaca — 90% com desfoque deixaria 10% de um campo que muda passando por baixo
do maior texto da página.

**Sobre a porta.** `GradientWaves` e `ShapeGrid` em TypeScript strict, sem
`any`. Movimento reduzido desenha um frame e não entra no laço — o `ShapeGrid`
nem tem laço para desligar. Sem WebGL2, o construtor cai no `try/catch` e o
gradiente estático que já está no DOM continua sendo o fundo. Pausa por aba
oculta e por `IntersectionObserver` sobreviveram, `dpr` segue limitado a 2, e o
raymarching cai para 40 passos abaixo de 640 px.

**Custo assumido.** `ogl` é a única dependência nova aqui (~30 kB gzip). O
bundle foi para 616 kB minificado, 191 kB em gzip. Sem code-splitting: o fundo
animado está na primeira tela, e adiá-lo não adiantaria o que ele adia.
