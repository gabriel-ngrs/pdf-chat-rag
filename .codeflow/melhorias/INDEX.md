---
versão: 1.0
status: estável
atualizado: 2026-08-17
schema_version: 1.0
---

# Melhorias do TalkDoc

Pedidos de melhoria levantados pelo owner depois do teste de ponta a ponta.
Diferente de `bugs/`, aqui não há defeito: são coisas que funcionam e podem
ficar melhores — legibilidade, identidade visual e movimento.

Cada melhoria é um documento numerado. O número é a ordem de chegada, não a
ordem de execução.

## Índice

| id | melhoria | área | prioridade | esforço | status |
|---|---|---|---|---|---|
| [MELH-001](001-legibilidade-da-resposta-do-chat.md) | Resposta do chat chega em Markdown e é exibida crua | frontend + prompt | alta | médio | aberto |
| [MELH-002](002-background-animado-e-paleta-escura.md) | Background animado (WebGL) e paleta mais escura | frontend | média | alto | aberto — depende de decisão do owner |
| [MELH-003](003-logo-da-yaitec-no-cabecalho.md) | Logo da Yaitec ao lado da marca TalkDoc | frontend | média | baixo | bloqueado — falta o arquivo da logo |
| [MELH-004](004-animacoes-de-interacao.md) | Animações de mouse, cards e textos | frontend | média | médio | aberto |

## Ordem sugerida de execução

1. **MELH-001** primeiro, sozinha. É a única que muda o que a pessoa consegue
   ler, e as outras três são sobre como a tela parece. Uma resposta bem
   formatada num fundo feio vale mais que o contrário.
2. **MELH-003** em seguida, assim que o arquivo da logo chegar — é a mais barata
   e não conflita com nada.
3. **MELH-002** e **MELH-004** juntas, nessa ordem. As duas mexem em movimento e
   em paleta, e o parallax de mouse pedido na 004 é o mesmo do fundo da 002 —
   fazer separado significa refazer.

## Dependências entre elas

- A **MELH-002** precisa de três decisões do owner (o que "mais escura"
  significa, quais cores o shader usa, em que telas o fundo aparece) antes de
  qualquer linha de código. As decisões vão para `.codeflow/decisions/`.
- A **MELH-003** está bloqueada por um arquivo que só o owner tem: a logo em
  SVG. O `Exemplo-YAITEC.pdf` foi verificado e não contém imagem embutida.
- A **MELH-004** herda da **MELH-002** a decisão sobre parallax de ponteiro. Se
  a 002 for adiada, a 004 sai sem essa parte.

## Fronteira com `bugs/`

A `MELH-001` encosta no [BUG-005](../bugs/005-resposta-cita-trecho-n-que-nao-existe-na-interface.md):
os dois mexem no texto da resposta e em `ANSWER_INSTRUCTIONS`. A diferença é que
o BUG-005 é defeito (a resposta cita um rótulo que a tela não tem) e a MELH-001 é
legibilidade (o Markdown não é renderizado). Devem ser resolvidos na mesma
passada pelo prompt.

## Restrições que valem para todas

Vêm da `constitution.md` e do cabeçalho de `frontend/src/index.css`, e nenhuma
melhoria as afrouxa:

- cor **sempre** por token semântico — nenhum hex e nenhuma cor Tailwind crua
  dentro de componente;
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

## Versão do schema e última atualização

Schema 1.0 | Última atualização: 2026-08-17 | Origem: pedido do owner após o teste de ponta a ponta
