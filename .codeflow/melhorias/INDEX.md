---
versão: 1.0
status: estável
atualizado: 2026-08-18
schema_version: 1.0
---

# Melhorias do TalkDoc

Pedidos de melhoria levantados pelo owner depois do teste de ponta a ponta.
Diferente de `bugs/`, aqui não há defeito: são coisas que funcionam e podem
ficar melhores — legibilidade, identidade visual, movimento e, a partir da
**MELH-005**, fluxo de uso.

Cada melhoria é um documento numerado. O número é a ordem de chegada, não a
ordem de execução.

## Índice

| id | melhoria | área | prioridade | esforço | status |
|---|---|---|---|---|---|
| [MELH-001](001-legibilidade-da-resposta-do-chat.md) | Resposta do chat chega em Markdown e é exibida crua | frontend + prompt | alta | médio | implementado (2026-08-18) |
| [MELH-002](002-background-animado-e-paleta-escura.md) | Background animado (WebGL) e paleta mais escura | frontend | média | alto | implementado (2026-08-18) |
| [MELH-003](003-logo-da-yaitec-no-cabecalho.md) | Logo da Yaitec ao lado da marca TalkDoc | frontend | média | baixo | implementado (2026-08-18) |
| [MELH-004](004-animacoes-de-interacao.md) | Animações de mouse, cards e textos | frontend | média | médio | implementado (2026-08-18) |
| [MELH-005](005-envio-de-varios-documentos-de-uma-vez.md) | Arrastar e soltar vários documentos de uma vez | frontend + backend + dados | média | médio (A) / alto (B) | aberto — análise de custo entregue |

**As quatro primeiras estão fechadas.** As decisões que faltavam foram tomadas com o owner
na abertura do trabalho e estão em
[`decisions/2026-08-18-paleta-yaitec-e-fundos-das-telas.md`](../decisions/2026-08-18-paleta-yaitec-e-fundos-das-telas.md).

## Ordem em que foram executadas

A ordem sugerida foi seguida, com um ajuste: a **MELH-003** saiu junto da
**MELH-002**, porque a paleta de uma e a logo da outra dividem o mesmo cabeçalho
e o mesmo conjunto de tokens — separá-las significaria pintar o `AppShell` duas
vezes.

1. **MELH-001** — renderizador de Markdown e o vazamento dos rótulos na cópia.
2. **MELH-002** e **MELH-003** — paleta da Yaitec, os dois fundos, e a logo.
3. **MELH-004** — o movimento, por último, sobre a paleta já assentada.

A **MELH-005** chegou depois desse bloco, durante o teste do sistema, e é de
outra natureza: não é acabamento, é funcionalidade. Ela está **aberta** e o que
existe é a análise de custo — o documento mede dois escopos (envio em lote com
uma conversa por documento; conversa sobre vários documentos ao mesmo tempo) e
recomenda o primeiro. A execução depende da escolha do owner e, no escopo maior,
de spec própria: ele mexe em banco, retrieval e citação.

## Como as dependências se resolveram

- As três decisões da **MELH-002** vieram do owner: paleta do site da
  yaitec.com; `GradientWaves` na tela de envio e `ShapeGrid` **estático** na
  tela de chat; cores do shader saindo dos tokens.
- O bloqueio da **MELH-003** saiu com o arquivo entregue pelo owner. Ele não era
  vetor — 538 kB de PNG embrulhado em SVG, sobre fundo navy chapado —, e o
  desenho foi vetorizado a partir dele para 1 kB em `currentColor`.
- O parallax de ponteiro ficou na **MELH-002**, no fundo animado, como previsto.
  A **MELH-004** herdou dali só o hook de movimento reduzido.

## Fronteira com `bugs/`

A `MELH-001` encosta no [BUG-005](../bugs/005-resposta-cita-trecho-n-que-nao-existe-na-interface.md):
os dois mexem no texto da resposta e em `ANSWER_INSTRUCTIONS`. A diferença é que
o BUG-005 é defeito (a resposta cita um rótulo que a tela não tem) e a MELH-001 é
legibilidade (o Markdown não é renderizado). Foram resolvidos na mesma passada
pelo prompt, como este índice pedia: `ANSWER_INSTRUCTIONS` recebeu de uma vez a
regra de citar só a página e a regra de formato.

## Restrições que valem para todas

Vêm da `constitution.md` e do cabeçalho de `frontend/src/index.css`, e nenhuma
melhoria as afrouxa:

- cor **sempre** por token semântico — nenhum hex e nenhuma cor Tailwind crua
  dentro de componente. Os fundos em canvas resolvem isso lendo os tokens em
  tempo de execução (`lib/colors.ts` + `hooks/useTokenColors.ts`), porque um
  canvas não herda `var(--highlight)`: ele quer três números;
- `prefers-reduced-motion` é respeitado; animação em JS precisa checar a media
  query por conta própria, porque a regra do CSS não a alcança;
- `tsc --strict` sobre `frontend/src`, sem `any`;
- dependência nova passa por `npm audit --audit-level=high`;
- texto de interface em pt-BR;
- `make check` verde antes de fechar qualquer uma.

## Ferramental de design disponível no projeto

Três skills foram adicionadas em `.claude/skills/` para este trabalho:

- `impeccable` — auditoria e polimento de interface, tokens, motion, a11y;
- `ui-ux-pro-max` — base de estilos, paletas, pareamentos tipográficos;
- `frontend-design` — geração de interface com padrão de acabamento alto.

## O que as quatro deixaram no projeto

Arquivos novos que passam a ser referência para o que vier depois:

- `components/Markdown.tsx` — Markdown do modelo virando tokens do design
  system, com HTML exibido como texto e nunca executado;
- `components/YaitecMark.tsx` — a logo em `currentColor`, e o
  `public/favicon.svg` que sai dela;
- `components/backgrounds/` — `GradientWaves` (WebGL), `ShapeGrid` (estático) e
  o `AppBackground` que escolhe entre eles e os recorta para longe do texto;
- `hooks/useReducedMotion.ts` — a única porta por onde passa qualquer coisa que
  se mova por JS neste projeto;
- `hooks/usePointerSpotlight.ts` e `hooks/useTokenColors.ts`;
- `lib/colors.ts` — token CSS virando sRGB, pelo canvas.

## Versão do schema e última atualização

Schema 1.0 | Última atualização: 2026-08-18 | Origem: pedido do owner após o teste de ponta a ponta
