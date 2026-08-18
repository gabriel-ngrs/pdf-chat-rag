---
spec: 02-chat-rag
fase: B.3
slug_fase: citations
tentativa: 2
veredito: APROVADO
score: 9.7
threshold: 8.5
range_avaliado: 199ce9f..e696ab7
---

# FASE B.3 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.7 / threshold 8.5

O gate desta fase é o mais caro de falsificar e o mais fácil de conferir: a
página que o chip declara tem de ser a página de onde o trecho saiu. **Refiz a
verificação eu mesma, com uma consulta ao banco do compose que junta cada
citação ao chunk de origem — cinco de cinco batem.** Zero BLOQUEANTES, zero
IMPORTANTES.

> **Nota sobre `range_avaliado`:** o EXECUCAO declara `199ce9f..3d10f34`, a ponta
> da tentativa 1. Auditei o span real. Ver S-1 na `B.1`.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 4 | Gate fechado e reconferido por mim (§3): 5 citações reais, página correta em todas, `snippet` entre 227 e 238 chars exibido inteiro, `Tab`→`Enter`→`Esc` com devolução de foco. Escopo travado: nada recortado no cliente, nada fabricado (agora nem `chunk_index`/`score` têm default), cor fora de token → 0. Desconto por A-1 (§5): dois chips da mesma página têm nome acessível idêntico |
| 2 | Arquitetura e direção de dependências | 3 | 5 | Componente de apresentação puro, sem estado nem I/O; `MessageList` compõe |
| 3 | Segurança / LGPD | 3 | 5 | Só renderiza o que veio no evento; o React escapa o `snippet`, que é conteúdo de PDF de terceiro; grep de segredo → 0 |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `Badge` e `Dialog` do design system sobre Radix — foco, `Esc` e devolução de foco não foram reimplementados, e o gate provou que funcionam |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Similaridade com vírgula decimal (`similaridade 0,74` na captura); rótulos em pt-BR, identificadores em inglês |
| 6 | Local e nomes dos arquivos | 2 | 5 | Exatamente a lista da §5; **zero desvio** — segue a única fase do track nessa situação |
| 7 | Qualidade de código | 2 | 5 | 68 linhas, uma responsabilidade, ordenação estável sem mutar a entrada |
| 8 | Testes e cobertura | 2 | 5 | 6 testes offline sobre comportamento, mais o gate real que cobre o que teste offline não alcança (a página de verdade) |
| 9 | Migration safety | 2 | — | Não se aplica |

Média ponderada: 97/20 = 4,85 → **9.7/10**.

## 3. Achados BLOQUEANTES

Nenhum. O B-1 da tentativa 1 está fechado.

**Minha verificação independente.** Peguei a última resposta fundamentada do
banco do compose (`messages.id = 60`, 5 citações) e juntei cada citação ao chunk
que ela declara, conferindo *(a)* se a página da citação é a página real do
chunk e *(b)* se o começo do `snippet` está mesmo dentro do `content` daquele
chunk:

```text
cit_chunk | cit_page | chunk_page_real | trecho_esta_na_pagina
----------+----------+-----------------+-----------------------
 0        | 1        |               1 | t
 3        | 1        |               1 | t
 5        | 2        |               2 | t
 6        | 2        |               2 | t
 8        | 3        |               3 | t
```

Cinco de cinco. E o recorte do servidor cabe no teto: comprimentos 227, 231,
233, 236 e 238 caracteres, todos ≤ 240, com `score` em `[0,1]` decrescente
(0,768 · 0,757 · 0,737 · 0,731 · 0,730). A captura `gate-b/14-dialogo-citacao.png`
mostra o diálogo aberto com página, trecho inteiro, `similaridade 0,74` discreta
no rodapé e o anel de foco visível no botão de fechar.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **A-1 — Dois chips da mesma página têm o mesmo nome acessível.** Na resposta
  do gate saíram `ver trecho da página 1`, `ver trecho da página 2`,
  `ver trecho da página 2`, `ver trecho da página 3`, `ver trecho da página 3`.
  Quem navega por leitor de tela ouve o mesmo nome duas vezes seguidas para
  botões que abrem trechos diferentes, sem nada que os distinga. Não reprova —
  não há critério WCAG que proíba nomes repetidos —, mas é o tipo de detalhe que
  o eixo de acessibilidade da spec (NFR-10) cobra. É uma linha no `aria-label`
  de `CitationChip.tsx:43`, por exemplo acrescentando a ordem do trecho na
  página. Mantenho a recomendação de **não** deduplicar os chips: esconder um
  trecho realmente usado mostraria menos fundamentação do que houve.
- **Ver S-1 e S-2 na avaliação da `B.1`** (frontmatter fora do schema; linha
  "Não se aplica — primeira execução." sobrando em
  `FASE-B.3-citations-EXECUCAO.md:157`).

## 6. Comandos rodados + saídas reais

```text
$ make check
Contracts: 4 kept, 0 broken.
===================== 263 passed, 19 deselected in 14.35s ======================
 Test Files  10 passed (10)
      Tests  84 passed (84)

$ make security
No known vulnerabilities found | found 0 vulnerabilities | SEC_EXIT=0

# escopo travado: nenhuma cor crua nos arquivos da fase
$ grep -nE "#[0-9a-fA-F]{3,6}|(text|bg|border)-(gray|slate|zinc|…)-[0-9]" \
    frontend/src/components/CitationChip.tsx frontend/src/components/MessageList.tsx
(nenhuma linha)

# o gate, reconferido por mim no banco do compose
$ docker exec …db-1 psql -c "
    select (c->>'chunk_index'), (c->>'page_number'), ch.page_number,
           position(left(c->>'snippet',60) in ch.content) > 0
    from messages m join jsonb_array_elements(m.citations) c on true
    join chunks ch on ch.chunk_index = (c->>'chunk_index')::int
    where m.id = 60"
0|1|1|t   3|1|1|t   5|2|2|t   6|2|2|t   8|3|3|t

$ docker exec …db-1 psql -c "… length(snippet), score … where m.id=60"
238/0.768 · 227/0.757 · 233/0.737 · 236/0.731 · 231/0.730

$ git status --short
(só um arquivo do Track A, de chat paralelo; nada meu)
```

## 7. Itens da fase / DoD não atendidos

Nenhum. O item aberto na tentativa 1 — "citações reais do `Exemplo-YAITEC.pdf`
exibidas, expansíveis e navegáveis por teclado" — está fechado nas três partes,
e a primeira eu reconferi por conta própria.

## 8. Divergências entre o relatório e o código real

- **A de S-1** (`range` desatualizado).
- **Nenhuma outra.** A tabela do §10 do relatório (5 citações, páginas 2/2/1/3/1,
  227–238 chars) é de um turno diferente do que eu inspecionei no banco, e as
  duas medições contam a mesma história: página correta em todas, recorte dentro
  do teto. A afirmação "conferência automatizada trecho→página" se sustenta —
  refiz a conferência por outro caminho e cheguei ao mesmo resultado.
