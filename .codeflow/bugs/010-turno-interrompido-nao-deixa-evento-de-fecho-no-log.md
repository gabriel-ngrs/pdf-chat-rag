---
id: BUG-010
titulo: "Turno interrompido não deixa evento de fecho no log, e `chat.client_disconnected` nunca dispara"
descoberto_em: 2026-08-18
descoberto_por: segunda rodada do roteiro de ponta a ponta, verificação dos logs (blocos 7 e 10)
severidade: baixa
fase_dona: A.4 (chat-endpoint, dona de `chat.py`)
status: aberto
---

# BUG-010 — O log mostra um turno que começa e nunca termina

## Sintoma

Quando o cliente cancela a resposta ou dá `F5` no meio do streaming, o log do
turno fica assim:

```json
{"conversation_id":"abdffed2…","question_len":84,"event":"chat.turn_started"}
{"conversation_id":"abdffed2…","candidates":5,"above_threshold":5,"top_score":0.782,"event":"chat.retrieved"}
```

E nada mais. Não sai `chat.generated`, não sai `chat.error`, não sai
`chat.client_disconnected`. Quem lê o log vê uma requisição que entrou, buscou
os trechos e sumiu — indistinguível de um turno travado no provedor.

O `chat.client_disconnected` tem **zero ocorrências** em toda a sessão de teste,
apesar de dois cancelamentos e dois `F5` no meio do stream:

```
$ docker compose logs backend | grep -c client_disconnected
0
```

**A persistência não sofre.** Os três casos gravaram normalmente, com
`truncated = true`:

```
 id | role      | truncated | len | inicio
 32 | assistant | t         | 664 | A YAITEC Solutions é uma startup brasileira especializada em
 34 | assistant | t         | 889 | A YAITEC Solutions é uma startup brasileira focada no mercad
 36 | assistant | t         |   9 | Segundo o
```

E a interface faz a coisa certa: ao voltar do `F5`, a resposta aparece marcada
*"Resposta interrompida antes do fim."* O defeito é só de observabilidade — mas
é justamente na interrupção que se quer o log.

## Causa raiz

`chat.py:294-317`. A guarda de desconexão mora **dentro** do laço, e é
consultada no começo de cada volta:

```python
async for piece in stream:
    if await is_disconnected():
        logger.warning("chat.client_disconnected", ...)
        break
    parts.append(piece)
    yield ChatEvent(TOKEN_EVENT, {"text": piece})
```

Quando o cliente aborta, o Starlette fecha o gerador da resposta. O fechamento
levanta `GeneratorExit` **no `yield`** — dentro da volta corrente, antes de o
`async for` pedir o próximo pedaço. O laço nunca chega à volta seguinte, então
a linha do `is_disconnected()` nunca é alcançada.

O `finally` roda (é o que grava a mensagem truncada, e é por isso que o banco
está correto), mas o `logger.info("chat.generated", ...)` está **depois** do
`try/finally`, no corpo normal da função:

```python
finally:
    await _close_stream(stream)
    stored = await _persist_answer(...)      # <- roda

logger.info("chat.generated", ...)           # <- nunca alcançado
```

O `GeneratorExit` continua propagando assim que o `finally` termina, e mata o
corpo restante. Persistência dentro do `finally` sobrevive; log fora dele, não.

O `is_disconnected()` só teria chance de disparar num cliente que para de ler
mas mantém a conexão aberta — que não é o que o navegador faz nem no
`AbortController` do `useChat` nem no `F5`. Na prática é código morto para os
dois caminhos que ele foi escrito para cobrir.

## Reprodução

1. Fazer uma pergunta que gere resposta longa.
2. Clicar em "Parar resposta" (ou dar `F5`) no meio do streaming.
3. `docker compose logs backend | grep -E 'chat\.(turn_started|retrieved|generated|client_disconnected)'`
   — o `request_id` do turno aparece nas duas primeiras linhas e em nenhuma
   terceira.
4. `select truncated from messages order by id desc limit 1;` → `t`. A gravação
   aconteceu; o log é que não registrou o fecho.

## Correção sugerida

Mover o evento de fecho para **dentro** do `finally`, junto da persistência, com
o motivo do fecho como campo:

```python
finally:
    await _close_stream(stream)
    stored = await _persist_answer(...)
    logger.info(
        "chat.generated",
        conversation_id=str(conversation.id),
        token_count=len(parts),
        truncated=truncated,
        duration_ms=_elapsed_ms(started),
    )
```

Com `truncated` já dizendo o que aconteceu, um turno interrompido passa a sair
como `chat.generated` com `truncated: true` — que é a mesma informação que a
interface e o banco já carregam, e fecha o `grep` por `request_id`.

O `chat.client_disconnected` pode então sair, ou virar `debug`: hoje ele promete
um sinal que o runtime não entrega, e um evento que nunca dispara é pior que
evento nenhum — quem procurar por ele vai concluir que ninguém desconectou.

Cuidado ao mexer: emitir log dentro de um `finally` que está processando
`GeneratorExit` não pode `await` nada que ceda o controle de volta ao event loop
sem necessidade. `structlog` com `PrintLoggerFactory` é síncrono, então está
seguro — mas isso é premissa a manter escrita ali.

## Teste de regressão

`tests/test_chat_api.py` já exercita o caminho de desconexão (é o que prova o
`truncated = true`). Acrescentar a asserção de que um `chat.generated` com
`truncated: true` foi emitido — o projeto já tem `tests/test_logging.py`, então
existe padrão de captura de evento para reaproveitar.

## Encaminhamento

Rework da `A.4` (chat-endpoint) da `02-chat-rag`, ou `/bugfix` — é uma mudança
de cinco linhas com teste. Prioridade baixa: nada visível ao usuário depende
disso. Vale antes da entrega mesmo assim, porque o log é parte do que um
avaliador olha, e "turno que começa e não termina" lê como bug maior do que é.
