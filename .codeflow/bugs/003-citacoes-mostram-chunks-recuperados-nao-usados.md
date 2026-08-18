---
id: BUG-003
titulo: "As citações exibem todos os chunks recuperados, não os que a resposta usou"
descoberto_em: 2026-08-17
descoberto_por: teste de ponta a ponta do owner (blocos 2 e 5 do roteiro)
severidade: média
fase_dona: A.4 (chat-endpoint)
status: aberto
---

# BUG-003 — Cinco chips de citação para uma resposta que usou um trecho

## Sintoma

Toda resposta exibe **cinco** chips de página, independentemente de quantos
trechos ela de fato usou. Exemplos das telas do teste:

| pergunta | o que a resposta diz | chips exibidos |
|---|---|---|
| `contato@yaitec.com` | "página 3, Trecho 5" | páginas 1, 2, 2, 3, 3 |
| `UFPB` | "página 2, Trechos 1 e 2" | páginas 1, 2, 2, 3, 3 |
| `A YAITEC trabalha com a StartStak?` | "Trecho 1, página 2" | páginas 1, 1, 2, 2, 3 |

O usuário vê cinco fontes; o texto aponta uma. Quem clicar nos outros quatro
chips encontra trechos que não têm relação com a resposta — e a leitura natural é
que o sistema citou errado.

## Causa raiz

`backend/app/chat.py::_to_citations` converte **todos** os chunks que passaram do
limiar em `Citation`, e o evento `citations` os emite inteiros. Não há filtro
entre "recuperado" e "usado".

FR-8 diz, com estas palavras: *"um evento `citations` traz `{page_number,
snippet, chunk_index, score}` **dos chunks usados**"*. O que o código emite é a
lista dos chunks **recuperados acima do limiar** — que é um conjunto maior.

Com `RETRIEVAL_TOP_K=5` e um documento pequeno, quase toda pergunta traz os cinco.

**Agravante:** como o documento tem três páginas e vêm cinco chunks, os rótulos
repetem — `página 1 · página 2 · página 2 · página 3 · página 3`. Dois chips
dizem a mesma coisa e o usuário não tem como saber qual sustenta a afirmação.
Ver também o [BUG-005](005-resposta-cita-trecho-n-que-nao-existe-na-interface.md).

## Por que passou pelos testes e pelas avaliações

`test_chat_api.py::test_citacoes_trazem_pagina_trecho_indice_e_score` verifica a
**forma** de cada citação — página, trecho recortado, índice e score — e não a
correspondência entre o que foi citado e o que foi usado. É a asserção certa para
o que ela se propõe; o buraco é que ninguém asseriu a cardinalidade.

Nas avaliações eu li FR-8 como "os chunks que entraram no prompt", que é uma
leitura defensável do texto e é o que o código faz. A tela mostra que a leitura
do usuário é outra.

## Correção sugerida

Três caminhos, do mais barato ao mais correto:

1. **Aceitar e renomear na interface.** Trocar o rótulo de "citações" para algo
   como "trechos consultados". Custa uma string e deixa de mentir. É o que cabe
   antes da entrega.
2. **Pedir ao modelo os índices usados** e filtrar por eles. Exige mudar o prompt
   para devolver os índices em formato parseável, e cria um caminho novo de
   falha quando ele não obedece.
3. **Reduzir `RETRIEVAL_TOP_K`** de 5 para 3. Não resolve o problema conceitual,
   mas reduz o ruído — e interage com o [BUG-002](002-limiar-de-similaridade-recusa-perguntas-legitimas.md),
   então não mexa nos dois ao mesmo tempo sem remedir.

Se a escolha for a (1), o texto de FR-8 precisa acompanhar via `/create-spec`, do
mesmo jeito que FR-3 e AC-7 já foram corrigidos.

## Encaminhamento

Decisão do owner sobre qual caminho seguir. Se for código, é rework da `A.4`
(dona de `chat.py`) ou da `B.3` (dona da exibição), conforme a escolha.
