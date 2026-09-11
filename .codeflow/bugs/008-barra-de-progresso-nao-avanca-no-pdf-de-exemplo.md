---
id: BUG-008
titulo: "A barra de progresso da ingestão não avança com o PDF de exemplo: fica em 0% e some"
descoberto_em: 2026-08-18
descoberto_por: segunda rodada do roteiro de ponta a ponta, automatizada com Playwright (bloco 1)
severidade: média
fase_dona: A.4 (ingestion-pipeline) — configuração, não código
status: corrigido e verificado (/double-check 2026-08-18)
---

# BUG-008 — Progresso de 0% direto para o fim, no arquivo da demonstração

## Sintoma

Subindo o `documento-de-exemplo.pdf` e amostrando o DOM a cada 120 ms, o **único**
valor que a barra chega a exibir é:

```
0 de 10 trechos · 0%
```

2,2 s depois a tela já é a conversa. A barra aparece zerada, fica zerada e some.
É exatamente o comportamento que o roteiro pede para vigiar — "a barra **avança**
e não pula do 0 ao 100" — e acontece com o arquivo que vai para a demonstração.

Não há defeito de correção: o documento é indexado certo, os 10 chunks entram no
banco com embedding de 768 dimensões, e o estado final é `ready`. O que falha é
o que a barra comunica.

## Causa raiz

O progresso é gravado **por lote de embedding**, e não por chunk
(`ingestion.py:127-144`):

```python
for batch in _batched(chunks, settings.embedding_batch_size):
    embeddings.extend(await asyncio.to_thread(embedder.embed_documents, texts))
    await repository.update_progress(document_id, len(embeddings))
```

A docstring explica a decisão, e ela está certa:

> O progresso é gravado por lote, e não ao final, porque a ingestão de um
> documento no teto da spec passa de meio minuto: sem isso a tela ficaria
> parada em zero e pareceria travada (NFR-1).

Só que o `documento-de-exemplo.pdf` tem 3 páginas e 3.665 caracteres, o que vira
**10 chunks**, e `EMBEDDING_BATCH_SIZE=16`. Dez cabem em um lote. Um lote é uma
gravação, no fim — que é precisamente o cenário que a docstring diz querer
evitar.

Confirmado no log:

```json
{"chunk_count": 10, "event": "document.chunked"}
{"batch_index": 0, "batch_size": 10, "duration_ms": 1247, "event": "embedding.batch"}
{"chunk_count": 10, "total_duration_ms": 1863, "event": "document.ready"}
```

Um único `embedding.batch`. A regra funciona; o documento é que é pequeno demais
para ela morder. Um PDF de 20 páginas daria ~65 chunks, ~5 lotes e ~5 passos na
barra — e ninguém veria problema nenhum.

Some a isso o `POLL_INTERVAL_MS = 1_500` do `useDocumentStatus`: com a ingestão
inteira durando 1,9 s, existe no máximo uma consulta no meio do caminho, e ela
cai antes de o único lote fechar.

## Reprodução

`docker compose up --build` a partir de estado limpo, subir o
`documento-de-exemplo.pdf` e observar a barra. Ou, para não depender do olho:

```js
// no console, durante a ingestão
setInterval(() => {
  const b = document.querySelector('[aria-label="Progresso da leitura do documento"]')
  if (b) console.log(b.getAttribute('aria-valuetext'))
}, 120)
```

## Correção sugerida

Três caminhos, do mais barato ao mais correto:

1. **Baixar `EMBEDDING_BATCH_SIZE` para 4.** Uma linha no `.env` e no
   `.env.example`. O exemplo passa a render 3 lotes e a barra anda três vezes.
   Custo: mais chamadas ao provedor por documento (para o exemplo, 3 em vez de
   1), o que interage com a quota do plano gratuito — mas embedding e chat têm
   cotas separadas, e a ingestão acontece uma vez por documento.
2. **Gravar progresso também no início do lote**, com o total de chunks já
   despachados. Faz a barra andar em dois tempos por lote sem mudar quantas
   chamadas o provedor recebe. É honesto: "despachado" não é "pronto", e o
   `aria-valuetext` teria de dizer isso.
3. **Reduzir `POLL_INTERVAL_MS` enquanto `status === 'processing'`.** Sozinho
   não resolve — não há o que amostrar entre 0 e 10 —, mas acompanha qualquer
   uma das duas anteriores.

Recomendo a **1**, e só ela. É configuração, resolve o caso da demonstração, e
não acrescenta conceito novo à interface.

Vale registrar a alternativa honesta: **aceitar e não mostrar barra quando há um
lote só.** O esqueleto indeterminado que o componente já usa quando `chunks_total`
ainda não existe (`ProcessingStatus.tsx:181`) diria a verdade — "estou
trabalhando, não sei em quanto" — em vez de uma porcentagem que só conhece dois
valores. Custa menos que a 2 e não gasta chamada nenhuma.

## Encaminhamento

Rework da `A.4` (ingestion-pipeline) se for o caminho 2; se for o 1 ou a
alternativa, é decisão do owner mais uma linha de configuração — e vale um
registro em `decisions/`, porque mexer no tamanho do lote toca a área de alto
risco `adapters/` descrita na constitution ("embeddings de documento vão em
lote, nunca uma requisição por chunk").
