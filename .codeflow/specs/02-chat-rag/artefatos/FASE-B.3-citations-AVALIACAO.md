---
spec: 02-chat-rag
fase: B.3
slug_fase: citations
tentativa: 1
veredito: REPROVADO
score: 9.4
threshold: 8.5
range_avaliado: 199ce9f..3d10f34
---

# FASE B.3 — Avaliação independente

## 1. Veredito e score

**Veredito:** REPROVADO · **Score:** 9.4 / threshold 8.5

O melhor score do track: zero desvio de arquivo, escopo travado inteiro provado
por teste, e a única dúvida que o próprio executor levantou (contraste do chip
marcado) eu **medi e ela passa com folga** — 10,68:1 no tema claro e 8,92:1 no
escuro, contra os 4,5:1 exigidos.

Reprova por **um BLOQUEANTE**: o critério de conclusão — *"citações reais de uma
pergunta sobre o `Exemplo-YAITEC.pdf` exibidas"* — não foi cumprido.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 3 | AC-18 provado (`CitationChip.test.tsx:19` — `userEvent.tab()` põe o foco no chip, `{Enter}` abre o diálogo com página e trecho); AC-19 parte da B.3 (`MessageList.test.tsx:83` — sem citação, nem chip nem lista rotulada). Escopo travado: snippet não recortado no cliente (teste com 241 chars, `CitationChip.test.tsx:33`), nada fabricado (`CitationChip.tsx:34-67` só lê o que recebe), cor fora de token → grep 0. **Gate com citação real não cumprido** (§3) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | Componente de apresentação puro, sem estado próprio nem I/O; `MessageList` compõe, não conhece o chip por dentro |
| 3 | Segurança / LGPD | 3 | 5 | Só renderiza o que veio no evento; o React escapa o `snippet`, que é conteúdo de PDF de terceiro (`CitationChip.tsx:59`); nenhum segredo no diff |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `Badge` e `Dialog` do design system sobre Radix — foco, `Esc` e devolução de foco não foram reimplementados; tipo `Citation` é o da B.1; zero dependência nova |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Similaridade com vírgula decimal, como se escreve em pt-BR (`CitationChip.tsx:16`); `aria-label` descritivo em pt-BR; identificadores em inglês |
| 6 | Local e nomes dos arquivos | 2 | 5 | Exatamente a lista da §5: `CitationChip.tsx` novo, `MessageList.tsx` alterado. **Zero desvio** — a única fase do track nessa situação |
| 7 | Qualidade de código | 2 | 5 | 68 linhas, uma responsabilidade, ordenação estável sem mutar a entrada (`MessageList.tsx:87-90`, `[...citations].sort`) |
| 8 | Testes e cobertura | 2 | 5 | 6 testes novos cobrindo teclado, integridade do trecho, discrição do score e ausência da área; asserções sobre comportamento, não sobre implementação |
| 9 | Migration safety | 2 | — | Não se aplica |

Média ponderada: 94/20 = 4,7 → **9.4/10**.

## 3. Achados BLOQUEANTES

### B-1. Critério de conclusão da fase não cumprido — citação real do `Exemplo-YAITEC.pdf`

**Onde:** `SPEC_02_CHAT_RAG.md` §5, Fase B.3, *Critério de conclusão (gate)*;
`FASE-B.3-citations-EXECUCAO.md:126` marca PENDENTE.

O gate pede citações **reais** exibidas, expansíveis e navegáveis por teclado.
As três propriedades estão provadas contra dados de teste; o que falta é o dado
real. E aqui a exigência tem substância própria: é o gate que revela se o
`snippet` de 240 caracteres recortado pelo servidor cabe no diálogo sem quebrar
o layout, e se o número de página bate com o PDF aberto ao lado — que é a
demonstração inteira do eixo de fundamentação.

**Correção sugerida (sem mudar código):**
1. `make up` na `dev` atual, ingerir o `Exemplo-YAITEC.pdf`.
2. Perguntar algo que o documento responde; abrir cada chip.
3. Conferir **contra o PDF** que a página do chip contém o trecho mostrado —
   é a checagem que nenhum teste offline consegue fazer.
4. Percorrer os chips por `Tab`, abrir por `Enter`, fechar por `Esc`.
5. Registrar no EXECUCAO (tentativa 2) e reavaliar em chat zerado.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **Dúvida do EXECUCAO §9.2 resolvida a favor do que está lá:** o par
  `--highlight` / `--highlight-foreground` dá **10,68:1** (claro) e **8,92:1**
  (escuro). Passa AA e AAA. Não há o que remediar — o comentário no
  `index.css:137` ("superfície, nunca texto") continua valendo e a fase o
  respeitou, usando a cor como fundo do chip marcado.
- **Dúvida do EXECUCAO §9.1 (dois chips "página 4"):** manter como está. A
  decisão de não deduplicar é a correta para um app cujo eixo é fundamentação —
  esconder um trecho usado mostraria menos prova do que houve. Se algum dia
  incomodar, o rótulo do `aria-label` é o lugar de desempatar, não o texto
  visível.
- **Sanidade do dado exibido:** o `score` chega ao diálogo sem validação de
  faixa; um `score` ausente vira `0` lá atrás (`sse.ts:33`) e aparece como
  "similaridade 0,00". Ver a sugestão correspondente na avaliação da `B.2` — o
  conserto é no parser, não aqui.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ §5 estruturalmente válida
EXIT=0

$ git merge-base --is-ancestor 3d10f34 HEAD && echo ANCESTOR-OK
ANCESTOR-OK      # idem 199ce9f

$ git diff --stat 199ce9f..3d10f34 -- . ':(exclude).codeflow/specs/*/artefatos/*'
 frontend/src/components/CitationChip.test.tsx | 58 ++++++++++++++
 frontend/src/components/CitationChip.tsx      | 68 +++++++++++++++++
 frontend/src/components/MessageList.test.tsx  | 34 ++++++++++
 frontend/src/components/MessageList.tsx       | 38 +++++++--
 4 files changed, 194 insertions(+), 4 deletions(-)
# → exatamente os arquivos da §5, mais os testes

$ make check
Contracts: 4 kept, 0 broken.
===================== 248 passed, 17 deselected in 11.93s ======================
 Test Files  10 passed (10)
      Tests  75 passed (75)

$ make security
No known vulnerabilities found
found 0 vulnerabilities
SECURITY_EXIT=0

# escopo travado da B.3 — nenhuma cor crua nos arquivos da fase
$ grep -nE "#[0-9a-fA-F]{3,6}|(text|bg|border)-(gray|slate|zinc|neutral|stone|red|blue|green|purple)-[0-9]" \
    frontend/src/components/CitationChip.tsx frontend/src/components/MessageList.tsx
(nenhuma linha)

# contraste do chip marcado (OKLCH → sRGB → luminância relativa → WCAG)
LIGHT highlight-foreground sobre highlight   10.68:1   ✅ AA e AAA
DARK  highlight-foreground sobre highlight    8.92:1   ✅ AA e AAA

$ git status --short
(vazio — árvore limpa ao final)
```

## 7. Itens da fase / DoD não atendidos

- **Gate da §5:** citações reais do `Exemplo-YAITEC.pdf` exibidas — não cumprido
  (B-1). Expansão e navegação por teclado estão provadas offline; falta o dado
  real e a conferência página-a-página contra o PDF.
- **DoD §9 da spec:** "`B.3 citations` — citações exibidas, expansíveis e
  navegáveis por teclado" ⏳ (as duas últimas propriedades, sim; a primeira com
  dado real, não).
- **Elegibilidade (§2.11.4):** depende da `B.2`, que não está concluída. Mesma
  raiz do B-1 da `B.1`.

## 8. Divergências entre o relatório e o código real

Nenhuma. Verifiquei todas as afirmações do EXECUCAO:

- "chips ordenados por página, empate por `chunk_index`" — confere
  (`MessageList.tsx:87-90`), provado em `MessageList.test.tsx:62`.
- "similaridade só dentro do diálogo" — confere (`CitationChip.tsx:62-64`),
  com asserção de ausência no chip (`CitationChip.test.tsx:45`).
- "desvios: nenhum" — confere pelo `git diff --stat` acima.
- "trecho exibido como veio do servidor" — confere: não há `slice`, `substring`
  nem truncamento em `CitationChip.tsx`.
