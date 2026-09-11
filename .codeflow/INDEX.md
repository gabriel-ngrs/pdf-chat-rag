---
versão: 1.0
status: estável
atualizado: 2026-08-18
schema_version: 1.0
---

# INDEX do .codeflow/ do projeto

## Nota sobre anonimização — 2026-09-10

Este projeto nasceu de um escopo fechado com um cliente, e os documentos abaixo
são o registro de execução tal como foi escrito na época. Quando o repositório
foi aberto, **toda identificação do cliente saiu**: nome da empresa, marca, site,
nome de pessoas, clientes citados e o arquivo institucional que servia de
documento de teste.

O que ficou no lugar são descritores neutros — "o cliente", "a empresa do
documento", "o fundador", `documento-de-exemplo.pdf`. Números medidos, datas,
decisões, causas-raiz e vereditos não foram tocados: o registro continua sendo o
que aconteceu, sem os nomes de quem não pediu para estar aqui.

O documento de exemplo atual é `samples/lgpd-capitulos-1-2.pdf`, de domínio
público. Relatos anteriores a esta data se referem ao documento antigo, de três
páginas — por isso as contagens de página e de chunks divergem do que uma
execução de hoje produz.

## Leia sempre primeiro
1. `constitution.md` — regras invariantes deste projeto.
2. `manifest.md` — stack, comandos de validação, padrões definidos.

## Leia se relevante ao contexto
- `decisions/INDEX.md` — índice navegável de decisões. Filtrar por tag relevante antes de carregar decisions individuais.
- `specs/` — specs de feature e relatórios de fase, gerados por `/create-spec` e pelos workflows de execução.
- `melhorias/INDEX.md` — pedidos de melhoria do owner (legibilidade, identidade visual, motion). Numerados, um documento por melhoria.
- `bugs/INDEX.md` — índice dos defeitos encontrados nas duas rodadas do teste de ponta a ponta.
  Os cinco da 1ª rodada (`001`–`005`) e os cinco da 2ª (`006`–`010`, roteiro automatizado com
  Playwright) estão corrigidos e verificados. O índice guarda o relato de cada um, que é onde a
  causa raiz está escrita.
- `bug-batches/<slug>.md` — ledger de um lote de bugs: status por bug, o que reproduz cada um, o fix
  ancorado em `arquivo:linha` e o veredito do `/double-check`. Gerado por `/batch-bugfix`.

## Arquivos gerados automaticamente — não editar manualmente
- `checkpoints/*` — estado intermediário de workflows em execução. Efêmero, vai para `.gitignore`.
- `decisions/<data>-<titulo>.md` — decisões individuais. Geradas por workflows; alterações manuais quebram o índice.

## Versão do schema e última atualização
Schema 1.0 | Última atualização: 2026-08-18 | Gerado por: bootstrap
