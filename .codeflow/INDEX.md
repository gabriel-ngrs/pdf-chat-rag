---
versão: 1.0
status: estável
atualizado: 2026-08-18
schema_version: 1.0
---

# INDEX do .codeflow/ do projeto

## Leia sempre primeiro
1. `constitution.md` — regras invariantes deste projeto.
2. `manifest.md` — stack, comandos de validação, padrões definidos.

## Leia se relevante ao contexto
- `decisions/INDEX.md` — índice navegável de decisões. Filtrar por tag relevante antes de carregar decisions individuais.
- `specs/` — specs de feature e relatórios de fase, gerados por `/create-spec` e pelos workflows de execução.
- `melhorias/INDEX.md` — pedidos de melhoria do owner (legibilidade, identidade visual, motion). Numerados, um documento por melhoria.
- `bugs/INDEX.md` — índice dos defeitos encontrados no teste de ponta a ponta. Os cinco estão
  corrigidos e verificados; o índice guarda o relato de cada um, que é onde a causa raiz está escrita.
- `bug-batches/<slug>.md` — ledger de um lote de bugs: status por bug, o que reproduz cada um, o fix
  ancorado em `arquivo:linha` e o veredito do `/double-check`. Gerado por `/batch-bugfix`.

## Arquivos gerados automaticamente — não editar manualmente
- `checkpoints/*` — estado intermediário de workflows em execução. Efêmero, vai para `.gitignore`.
- `decisions/<data>-<titulo>.md` — decisões individuais. Geradas por workflows; alterações manuais quebram o índice.

## Versão do schema e última atualização
Schema 1.0 | Última atualização: 2026-08-18 | Gerado por: bootstrap
