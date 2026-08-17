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

## ✅ Gate executado na tentativa 2 (o aviso abaixo é da tentativa 1)

Cinco citações reais de uma pergunta sobre o `Exemplo-YAITEC.pdf` foram exibidas
e **conferidas página a página contra o PDF**. Evidências em §10.

## ⚠️ (Tentativa 1) Gate com dado real ainda PENDENTE

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
- [x] **Critério de conclusão com citação real do `Exemplo-YAITEC.pdf`**:
  cumprido na tentativa 2 (§10) — 5 chips reais, cada trecho conferido contra a
  página que o chip declara, abertos por `Tab`+`Enter` e fechados por `Esc`.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (6 novos; 68 no frontend)
- [x] `make check` zero
- [x] Escopo travado respeitado: snippet não é recortado no cliente; nada é
      fabricado; nenhuma cor fora dos tokens
- [x] Nenhum segredo no diff
- [x] Commits em pt-BR, Conventional Commits (`3d10f34`)
- [x] Gate com citação real — cumprido na tentativa 2 (§10)

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

## 10. Gate com citação real (tentativa 2, 2026-08-17)

Ambiente: `docker compose` da `dev` com a `A.4` mergeada, `Exemplo-YAITEC.pdf`
ingerido pela API do compose (3 páginas, 10 chunks, `status: ready`), navegador
dirigido por Playwright contra `http://localhost:5173` (o nginx do frontend, não
o dev server). Chave real do Gemini; nenhum dublê em nenhum ponto do caminho.

Pergunta: *"Quem fundou a YAITEC e qual a formação dele?"* — 5 citações, cada
`snippet` comparado com o texto extraído da página que o chip declara:

```text
página 2 | chunk_index 6 | score 0.761 | 231 chars | confere com a página 2? SIM
página 2 | chunk_index 5 | score 0.753 | 238 chars | confere com a página 2? SIM
página 1 | chunk_index 0 | score 0.707 | 227 chars | confere com a página 1? SIM
página 3 | chunk_index 8 | score 0.702 | 236 chars | confere com a página 3? SIM
página 1 | chunk_index 3 | score 0.701 | 233 chars | confere com a página 1? SIM

chips na tela: ['ver trecho da página 1', 'ver trecho da página 2',
                'ver trecho da página 2', 'ver trecho da página 3',
                'ver trecho da página 3']
foco por teclado em 'ver trecho da página 1'; Enter abriu o diálogo
Esc fechou; foco devolvido para 'ver trecho da página 1'
```

- **Citações reais exibidas:** os cinco chips vieram do turno real e estão
  ordenados por página, como a fase promete.
- **Página confere com o PDF:** conferência automatizada trecho→página contra o
  texto extraído do `Exemplo-YAITEC.pdf` — as cinco batem, nenhuma aparece em
  página diferente da declarada. É a verificação que nenhum teste offline faz.
- **Recorte do servidor cabe no diálogo:** os `snippet` chegaram entre 227 e 238
  caracteres (teto de 240) e o diálogo os mostrou inteiros, sem quebrar o layout
  (`14-dialogo-citacao.png`, com `similaridade 0,74` discreta no rodapé).
- **Teclado:** `Tab` alcança os chips, `Enter` abre, `Esc` fecha e devolve o foco
  ao chip de origem.

**Capturas:** `gate-b/02-resposta-com-chips.png`, `gate-b/14-dialogo-citacao.png`.
