---
spec: 02-chat-rag
fase: B.3
slug_fase: citations
status: executado
tentativa: 2
reprovacoes: 1
sha_inicial: 199ce9f
sha_final: 3d10f34
range: 199ce9f..3d10f34
---

# FASE B.3 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/Yaitec-TalkDoc-chatB`, branch
> `feat/chat-rag-trackB`.

## ⚠️ Gate com dado real ainda PENDENTE

O critério de conclusão pede "citações reais de uma pergunta sobre o
`Exemplo-YAITEC.pdf` exibidas". Com a `A.4` e a `A.3` do Track A ainda não
implementadas, não há de onde tirar citação real. O que está provado é a
renderização, a ordenação, a navegação por teclado e a ausência da área quando
não há citação — tudo contra o formato do evento `citations` da §4.3.

## 1. Resumo do que foi feito

Cada resposta passa a exibir, embaixo dela, um chip por trecho usado, rotulado
com a página e ordenado da página menor para a maior. Acionar o chip (clique,
`Enter` ou `Espaço`) abre um diálogo com o trecho e a similaridade. Resposta sem
citação não desenha área nenhuma.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `frontend/src/components/CitationChip.tsx` | O chip e o diálogo com trecho, página e similaridade |
| `frontend/src/components/CitationChip.test.tsx` | 4 testes: teclado, trecho íntegro, similaridade discreta, rótulo |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `frontend/src/components/MessageList.tsx` | Lista de citações ordenada sob a resposta (histórico e resposta em construção) |
| `frontend/src/components/MessageList.test.tsx` | +2 testes: ordenação por página e ausência da área sem citação |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `Badge` e `Dialog` são os do design system da `FEAT-0001
B.1`, sobre Radix — foco, `Esc` e devolução do foco ao chip já vêm resolvidos.
Nenhuma cor fora dos tokens: o chip usa `outline` e, no hover/foco, `bg-highlight`
com `text-highlight-foreground`. Nenhuma dependência nova. O tipo `Citation` é o
da `B.1`, derivado da §4.3.

**Decisões de design:**

1. **Diálogo, não tooltip, para o trecho.** Tooltip do Radix não é alcançável de
   forma confiável por toque e some ao mover o ponteiro — e o trecho tem até 240
   caracteres, que é conteúdo para ler, não dica. O diálogo também dá lugar
   natural para a similaridade.
2. **O marca-texto é o gesto do chip.** O sistema visual define `--highlight`
   como marca-texto e diz, no próprio arquivo de tokens, que ele marcaria a
   citação no chat. Em repouso o chip é discreto (`outline`); ao receber foco ou
   ponteiro, ele é marcado. É a identidade do produto aparecendo onde ela
   significa alguma coisa.
3. **A similaridade só existe dentro do diálogo.** No chip ela competiria com o
   número da página, que é o dado que a pessoa confere no PDF. Formatada com
   vírgula decimal, como se escreve em pt-BR.
4. **Ordenação por página e, no empate, por `chunk_index`.** Duas citações da
   mesma página aparecem na ordem em que estão no documento. Citações **não** são
   deduplicadas por página: cada chip corresponde a um trecho realmente usado, e
   esconder um deles seria mostrar menos fundamentação do que houve.
5. **A área de citações é `<ul>` com `aria-label`.** Sem o rótulo, um leitor de
   tela anuncia "lista de 2 itens" logo depois da resposta, sem dizer do que é a
   lista.

**Desvios:** nenhum. Arquivos exatamente os da §5 (`CitationChip.tsx` novo,
`MessageList.tsx` alterado), mais os testes correspondentes.

## 5. Comandos rodados + saídas reais

```text
# testes da fase
$ npx vitest run src/components/CitationChip.test.tsx src/components/MessageList.test.tsx
 Test Files  2 passed (2)
      Tests  9 passed (9)

# gate agregador
$ make check
...
====================== 135 passed, 6 deselected ======================
cd frontend && npm run test
 Test Files  10 passed (10)
      Tests  68 passed (68)

$ npx tsc --noEmit
TSC OK

# nenhuma cor crua nos arquivos da fase (esperado: 0)
$ grep -nE "#[0-9a-fA-F]{3,6}|text-(gray|slate|zinc)-" src/components/CitationChip.tsx src/components/MessageList.tsx | wc -l
0
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-18** (FR-17, NFR-10) — "é alcançável por Tab e revela trecho e página
  ao ser acionado": `userEvent.tab()` põe o foco no chip
  (`document.activeElement` é o botão), `{Enter}` abre o diálogo, e o teste
  confirma "Página 4" e o texto do trecho.
- [x] **AC-19, parte da `B.3`** (FR-18) — "não desenha área de citação quando a
  resposta não tem nenhuma": nem chip, nem a lista rotulada. (A aparência da
  recusa como resposta legítima é da `B.4`.)
- [x] **Chips rotulados com a página e ordenados** — teste "lista as citações da
  resposta ordenadas por página": entram como 7 e 2, saem como `página 2`,
  `página 7`.
- [x] **`aria-label` descritivo** — `ver trecho da página 4`, conferido por
  `getByRole('button', { name: ... })`.
- [x] **Não recortar o snippet no cliente** — teste com trecho de 241 caracteres:
  o `textContent` do diálogo é idêntico ao recebido.
- [x] **Não fabricar citação** — o componente só renderiza o que vem no evento;
  não há valor padrão para página, trecho ou score no caminho de exibição.
- [x] **Score discreto** — não aparece no chip (asserção de ausência) e aparece
  no diálogo como `similaridade 0,83`.
- [ ] **Critério de conclusão com citação real do `Exemplo-YAITEC.pdf`**:
  **PENDENTE**, depende de `A.3`/`A.4`.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (6 novos; 68 no frontend)
- [x] `make check` zero
- [x] Escopo travado respeitado: snippet não é recortado no cliente; nada é
      fabricado; nenhuma cor fora dos tokens
- [x] Nenhum segredo no diff
- [x] Commits em pt-BR, Conventional Commits (`3d10f34`)
- [ ] Gate com citação real — **pendente do Track A**

## 8. (Em rework) O que mudou nesta tentativa

Rework da avaliação `FASE-B.3-citations-AVALIACAO.md` (tentativa 1, REPROVADO,
score 9,4). Nenhuma mudança em `CitationChip.tsx` nem em `MessageList.tsx` —
não havia BLOQUEANTE de código nem IMPORTANTE, e o único bloqueio é o gate com
citação real do `Exemplo-YAITEC.pdf`, que continua aberto (topo deste relatório).

As duas dúvidas do §9 foram resolvidas pela avaliação, ambas a favor do que está
no código: o par `--highlight` / `--highlight-foreground` dá 10,68:1 (claro) e
8,92:1 (escuro), e a decisão de não deduplicar chips da mesma página fica como
está. A terceira observação — `score` chegando ao diálogo sem validação de faixa
— foi corrigida onde nasce, no parser da `B.2`: citação sem `score` ou sem
`chunk_index` passou a ser descartada em vez de completada com zero.

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **Duas citações da mesma página geram dois chips com o mesmo rótulo**
   ("página 4", "página 4"). É consequência da decisão 4 (não deduplicar). A
   alternativa seria numerar ("página 4 · trecho 2"); não fiz porque o número do
   chunk não significa nada para quem lê. Se o avaliador achar confuso, é uma
   linha no rótulo.
2. **Contraste do chip marcado.** `--highlight` com `--highlight-foreground` é o
   par que o design system declara para superfície marcada; não remedi o
   contraste desta combinação nesta fase — o par vem do sistema da `FEAT-0001`,
   que o declarou aprovado para superfície.
