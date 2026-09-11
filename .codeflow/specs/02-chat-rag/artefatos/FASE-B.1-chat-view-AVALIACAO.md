---
spec: 02-chat-rag
fase: B.1
slug_fase: chat-view
tentativa: 2
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: dd621eb..e696ab7
---

# FASE B.1 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

O BLOQUEANTE da tentativa 1 era o gate contra o backend real. Ele foi cumprido,
e eu **reproduzi a parte central dele por conta própria** contra o compose que
está no ar: `POST /api/conversations` pelo nginx (`:5173`) devolveu
`201 {"id": "ee3671ac-…"}`, e o par documento↔conversa está no `localStorage`
segundo as capturas. Zero BLOQUEANTES, zero IMPORTANTES.

> **Nota sobre `range_avaliado`.** O EXECUCAO desta tentativa declara
> `range: dd621eb..28159b6`, que é a ponta da **tentativa 1** — os commits do
> rework (`e76fbed`, `23799cc`, `e696ab7`) ficam de fora dele. Auditei o span
> real e é ele que este campo registra. Ver a sugestão S-1.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | Gate fechado: 1 `POST /api/conversations` → `201`, campo habilitado, `F5` com 0 conversas novas; os dois temas conferidos em `gate-b/04-chat-claro.png` e `05-chat-escuro.png`. AC-16 e AC-29 provados offline e agora confirmados na tela. Escopo travado: greps de cor crua, `EventSource`, segredo e estado global → **0** em todos |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `components/`/`hooks/`/`lib/` como a constitution manda; `mergeHistory` (`useChat.ts:44-47`) mantém a mescla do histórico dentro do hook dono do estado |
| 3 | Segurança / LGPD | 3 | 5 | `localStorage` guarda só dois ids; erro entra por `code`; grep de segredo → 0; `make security` sem achado |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Nenhum `fetch` novo; tokens e componentes do design system; zero dependência acrescentada |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Identificadores em inglês, UI em pt-BR; tipos derivados da §4.4 em `snake_case`, como o JSON |
| 6 | Local e nomes dos arquivos | 2 | 4 | `ProcessingStatus.tsx` continua fora da lista da §5 — desvio declarado desde a tentativa 1, justificado (prop opcional, evita polling duplicado) |
| 7 | Qualidade de código | 2 | 5 | Comentários registram o "porquê"; `isNearBottom` extraída como função pura (`MessageList.tsx:27-29`) sem inflar abstração |
| 8 | Testes e cobertura | 2 | 5 | A única lacuna da tentativa 1 (acompanhamento de scroll sem teste) foi fechada: `isNearBottom` virou função pura **com teste**. `mergeHistory` também ganhou cobertura |
| 9 | Migration safety | 2 | — | Não se aplica |

Média ponderada: 98/20 = 4,9 → **9.8/10**.

## 3. Achados BLOQUEANTES

Nenhum. O B-1 da tentativa 1 está fechado.

**Como confirmei, sem depender do relatório:**

```text
$ curl -s -X POST http://localhost:5173/api/conversations \
    -H 'Content-Type: application/json' -H 'X-Session-Id: avaliador' \
    -d '{"document_id":"b3d6b31d-f64e-479d-9475-8bb3f73c8dec"}'
{"id":"ee3671ac-0997-4960-b7d1-d7b378d9e038"}
```

O documento existe no banco do compose com `status: ready` e 3 páginas, e a
rota é a do nginx — o mesmo caminho que quem for usar o produto vai usar.
As capturas dos dois temas são reais e mostram a mesma composição (cabeçalho,
balão da pergunta, rótulo "RESPOSTA", chips, campo), legível nos dois.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **S-1 — Frontmatter do EXECUCAO fora do schema (§2.9.6).** Duas coisas:
  `status: executado` com `tentativa: 2` e `reprovacoes: 1` viola a regra 4
  (`executado` ⇒ tentativa 1 e reprovacoes 0; o valor certo é `rework`); e
  `sha_final`/`range` continuam apontando para `28159b6`, a ponta da tentativa
  anterior, quando §2.9.3 define `sha_final` como "HEAD após o trabalho **desta**
  tentativa". O efeito prático: um avaliador em chat zerado seguindo o `range`
  ao pé da letra auditaria o código **antes** do rework. Não retém a fase —
  nenhum consumidor deriva estado desses dois campos (§2.11.3 pareia por
  `tentativa`, e `status` é explicitamente denormalizado) —, mas os quatro
  relatórios devem ser corrigidos.
- **S-2 — Sobrou uma linha da tentativa 1** no §8 deste relatório
  (`FASE-B.1-chat-view-EXECUCAO.md:206`): "Não se aplica — primeira execução.",
  logo abaixo do texto que descreve o rework. Idem em `B.2` e `B.3`.
- **S-3 — A resposta mostra markdown cru.** Em `gate-b/06-f5-no-meio-do-stream.png`
  aparecem `### **1. Quem é a empresa**` e `* **Descrição e Foco:**` literais: o
  modelo devolve markdown e a tela renderiza como texto (`whitespace-pre-wrap`).
  A spec não pede renderização de markdown, então não é desvio — mas é o que
  quem abrir o produto vai ver.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ §5 estruturalmente válida
EXIT=0

$ for sha in dd621eb 28159b6 e76fbed 23799cc e696ab7; do git merge-base --is-ancestor $sha HEAD; done
(todos ancestrais de HEAD na dev)

$ make check
Contracts: 4 kept, 0 broken.
Required test coverage of 90% reached. Total coverage: 99.55%
===================== 263 passed, 19 deselected in 14.35s ======================
cd frontend && npm run test
 Test Files  10 passed (10)
      Tests  84 passed (84)

$ make security
No known vulnerabilities found
found 0 vulnerabilities
SEC_EXIT=0

# escopo travado (esperado 0 em todos)
EventSource: 0 | alert(: 0 | segredo: 0 | estado global: 0 | cor crua: 0

# o gate, reproduzido por mim contra o compose no ar
$ curl -s http://localhost:8000/api/health
{"status":"ok","database":"ok"}
$ docker exec …db-1 psql -c "select filename, status, page_count from documents"
 documento-de-exemplo.pdf | ready | 3
$ curl -s -X POST http://localhost:5173/api/conversations -d '{"document_id":"b3d6b31d-…"}'
{"id":"ee3671ac-0997-4960-b7d1-d7b378d9e038"}

$ git status --short
(só um arquivo do Track A, de chat paralelo; nada meu)
```

## 7. Itens da fase / DoD não atendidos

Nenhum. Os dois itens que ficaram abertos na tentativa 1 fecharam:

- "conversa criada contra o backend real" ✅ (reproduzido por mim).
- "layout consistente com o design system nos dois temas" ✅ (capturas 04 e 05,
  e as medições de contraste da tentativa 1, que já passavam AA).
- **Elegibilidade (§2.11.4):** a paralelização dos tracks com o gate da `A.4`
  aberto passou a ter decision registrada — `.codeflow/decisions/2026-08-17-paralelizacao-de-tracks-sem-gate-fechado.md`,
  no índice. O que faltava na tentativa 1 está sanado.

## 8. Divergências entre o relatório e o código real

- **Uma, e é a de S-1:** o `range` declarado não cobre a tentativa que o
  relatório descreve.
- Fora isso, nenhuma. Confirmei o contador de um único `POST`, o reuso da
  conversa guardada, a extração de `isNearBottom` com teste, e que as capturas
  citadas existem e mostram o que o texto diz.
