# Bugs do teste de ponta a ponta — FEAT-0002

Encontrados no teste de ponta a ponta do owner (2026-08-17), antes da fase `B.5`.
Nenhum se conserta dentro da `B.5`: cada um volta como rework da fase dona ou
como `/bugfix`, conforme a pré-condição registrada na spec.

> **Os cinco foram corrigidos em 2026-08-17** pelo lote
> `feat-0002-teste-ponta-a-ponta` — ledger em
> `.codeflow/bug-batches/feat-0002-teste-ponta-a-ponta.md`, decisões em
> `.codeflow/decisions/2026-08-17-lote-de-bugs-do-teste-de-ponta-a-ponta.md`.
> "Corrigido" aqui significa: fix aplicado, teste de regressão passando e
> reprodução do relato refeita contra a API real. **O `/double-check` rodou em
> 2026-08-18 e confirmou os cinco** — placar 5 ✓ · 0 ✗ · 0 ⚠, com cada teste de
> regressão reexecutado contra o código pré-fix e a reprodução refeita no
> compose. O veredito por bug está na seção "Verificação" do ledger.

| # | Título | Severidade | Fase dona | Status |
|---|--------|-----------|-----------|--------|
| [001](001-condensacao-nao-dispara-em-pergunta-de-4-palavras.md) | Continuação de 4 palavras não condensa e vira recusa falsa | **alta** | A.2 | corrigido |
| [002](002-limiar-de-similaridade-recusa-perguntas-legitimas.md) | Limiar 0,625 recusa perguntas que o documento responde | **alta** | A.5 | corrigido |
| [003](003-citacoes-mostram-chunks-recuperados-nao-usados.md) | Citações exibem os chunks recuperados, não os usados | média | A.4 | corrigido |
| [004](004-mensagem-de-quota-promete-um-minuto-mas-o-limite-e-diario.md) | Mensagem de quota promete "um minuto"; o limite é diário | média | B.4 / A.4 | corrigido |
| [005](005-resposta-cita-trecho-n-que-nao-existe-na-interface.md) | Resposta cita "Trecho N", rótulo que não existe na tela | média | A.2 | corrigido |

## Os dois que mais pesam

**001 e 002 se somam** e produzem o mesmo sintoma pela frente: recusa em pergunta
que o documento responde. A continuação não condensada chega ao retrieval como
frase vazia e pontua `0,527`; perguntas curtas sem a âncora "YAITEC" pontuam
entre `0,53` e `0,62`. O corte está em `0,625`.

A recusa é o mecanismo que o desafio avalia com mais peso. Falsa recusa é o pior
modo de falha: o sistema tem a informação, foi perguntado com clareza, e diz que
não sabe.

**003 e 005 se somam** também, e do lado da interface: cinco chips com rótulos
repetidos, e o texto apontando para uma numeração que não existe na tela.

## O que não é bug

O teste de estresse com Playwright (28 checagens) não encontrou mais nada. Upload,
validação de entrada, teclado, `aria-live`, foco visível, recusa sem banner de
erro, `F5` restaurando a sessão, duplo envio sem duplicar turno, chips por
teclado, `Escape`, tema escuro, troca de documento e cancelamento com texto
parcial preservado — todos corretos, sem erro de página nem de console.
