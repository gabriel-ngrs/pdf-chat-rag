import { describe, expect, it, vi } from 'vitest'

import { parseChatStream } from '@/lib/sse'
import type { ChatStreamEvent } from '@/lib/sse'

const encoder = new TextEncoder()

function streamOf(chunks: (string | Uint8Array)[], onCancel = vi.fn()): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk)
      }
      controller.close()
    },
    cancel: onCancel,
  })
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

async function collect(response: Response): Promise<ChatStreamEvent[]> {
  const events: ChatStreamEvent[] = []
  for await (const event of parseChatStream(response)) {
    events.push(event)
  }
  return events
}

describe('parseChatStream', () => {
  it('lê os quatro eventos do protocolo', async () => {
    const events = await collect(
      streamOf([
        'event: token\ndata: {"text":"A YAITEC "}\n\n',
        'event: token\ndata: {"text":"oferece consultoria."}\n\n',
        'event: citations\ndata: {"citations":[{"page_number":4,"snippet":"trecho","chunk_index":7,"score":0.83}]}\n\n',
        'event: done\ndata: {"message_id":12,"truncated":false}\n\n',
      ]),
    )

    expect(events).toEqual([
      { type: 'token', text: 'A YAITEC ' },
      { type: 'token', text: 'oferece consultoria.' },
      {
        type: 'citations',
        citations: [{ page_number: 4, snippet: 'trecho', chunk_index: 7, score: 0.83 }],
      },
      { type: 'done', messageId: 12, truncated: false },
    ])
  })

  it('junta um quadro que chegou partido entre dois chunks', async () => {
    const events = await collect(
      streamOf(['event: tok', 'en\ndata: {"text":"me', 'tade"}\n\nevent: token\ndata: {"text":"!"}\n\n']),
    )

    expect(events).toEqual([
      { type: 'token', text: 'metade' },
      { type: 'token', text: '!' },
    ])
  })

  it('não corrompe caractere multibyte partido entre chunks', async () => {
    const bytes = encoder.encode('event: token\ndata: {"text":"ação"}\n\n')
    // O "ç" ocupa dois bytes; o corte cai no meio dele de propósito.
    const cut = bytes.indexOf(0xc3)
    const events = await collect(streamOf([bytes.slice(0, cut + 1), bytes.slice(cut + 1)]))

    expect(events).toEqual([{ type: 'token', text: 'ação' }])
  })

  it('ignora comentário de keep-alive e evento desconhecido', async () => {
    const events = await collect(
      streamOf([
        ': ping\n\n',
        'event: barulho\ndata: {"seja":"o que for"}\n\n',
        'event: token\ndata: {"text":"ok"}\n\n',
      ]),
    )

    expect(events).toEqual([{ type: 'token', text: 'ok' }])
  })

  it('aceita o último quadro mesmo sem a linha em branco final', async () => {
    const events = await collect(streamOf(['event: done\ndata: {"message_id":3,"truncated":true}']))

    expect(events).toEqual([{ type: 'done', messageId: 3, truncated: true }])
  })

  it('descarta payload que não corresponde ao contrato', async () => {
    const events = await collect(
      streamOf([
        'event: token\ndata: {"text":42}\n\n',
        'event: token\ndata: isto não é json\n\n',
        'event: citations\ndata: {"citations":[{"snippet":"sem página"},{"page_number":2,"snippet":"boa"}]}\n\n',
        'event: done\ndata: {}\n\n',
      ]),
    )

    expect(events).toEqual([
      { type: 'citations', citations: [{ page_number: 2, snippet: 'boa', chunk_index: 0, score: 0 }] },
      { type: 'done', messageId: null, truncated: false },
    ])
  })

  it('normaliza o evento de erro do servidor', async () => {
    const events = await collect(
      streamOf(['event: error\ndata: {"code":"limite_de_uso","message":"Espere um minuto."}\n\n']),
    )

    expect(events).toEqual([
      { type: 'error', code: 'limite_de_uso', message: 'Espere um minuto.' },
    ])
  })

  it('fecha a leitura quando quem consome desiste no meio', async () => {
    const onCancel = vi.fn()
    const response = streamOf(
      ['event: token\ndata: {"text":"um"}\n\n', 'event: token\ndata: {"text":"dois"}\n\n'],
      onCancel,
    )

    for await (const event of parseChatStream(response)) {
      expect(event).toEqual({ type: 'token', text: 'um' })
      break
    }

    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
