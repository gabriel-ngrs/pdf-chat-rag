import { ApiError } from '@/lib/api'
import type { Citation } from '@/lib/types'

/**
 * Os quatro eventos do protocolo da FEAT-0002 §4.3, já validados.
 *
 * O que chega pela rede é `unknown`: um campo faltando ou com outro tipo não
 * pode virar `undefined` circulando pela interface até estourar longe da causa.
 */
export type ChatStreamEvent =
  | { type: 'token'; text: string }
  | { type: 'citations'; citations: Citation[] }
  | { type: 'error'; code: string; message: string }
  | { type: 'done'; messageId: number | null; truncated: boolean }

function readCitations(value: unknown): Citation[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.flatMap((item): Citation[] => {
    if (typeof item !== 'object' || item === null) {
      return []
    }
    const record = item as Record<string, unknown>
    if (typeof record.page_number !== 'number' || typeof record.snippet !== 'string') {
      return []
    }
    return [
      {
        page_number: record.page_number,
        snippet: record.snippet,
        chunk_index: typeof record.chunk_index === 'number' ? record.chunk_index : 0,
        score: typeof record.score === 'number' ? record.score : 0,
      },
    ]
  })
}

function toEvent(name: string, payload: string): ChatStreamEvent | null {
  let data: unknown
  try {
    data = JSON.parse(payload)
  } catch {
    return null
  }
  if (typeof data !== 'object' || data === null) {
    return null
  }
  const record = data as Record<string, unknown>

  switch (name) {
    case 'token':
      return typeof record.text === 'string' ? { type: 'token', text: record.text } : null
    case 'citations':
      return { type: 'citations', citations: readCitations(record.citations) }
    case 'error':
      return {
        type: 'error',
        code: typeof record.code === 'string' ? record.code : 'erro_interno',
        message: typeof record.message === 'string' ? record.message : '',
      }
    case 'done':
      return {
        type: 'done',
        messageId: typeof record.message_id === 'number' ? record.message_id : null,
        truncated: record.truncated === true,
      }
    default:
      // Evento que este cliente não conhece (inclusive o `ping` de keep-alive)
      // é ignorado de propósito: o protocolo pode crescer sem quebrar a tela.
      return null
  }
}

/**
 * Interpreta um quadro SSE (`event:` + uma ou mais linhas `data:`).
 *
 * Linha iniciada por `:` é comentário — é assim que o keep-alive do servidor
 * mantém a conexão viva —, e quadro sem `data` não vira evento.
 */
function parseFrame(frame: string): ChatStreamEvent | null {
  let name = 'message'
  const data: string[] = []

  for (const line of frame.split('\n')) {
    if (line === '' || line.startsWith(':')) {
      continue
    }
    const separator = line.indexOf(':')
    const field = separator === -1 ? line : line.slice(0, separator)
    const value = separator === -1 ? '' : line.slice(separator + 1).replace(/^ /, '')
    if (field === 'event') {
      name = value
    } else if (field === 'data') {
      data.push(value)
    }
  }

  return data.length > 0 ? toEvent(name, data.join('\n')) : null
}

/**
 * Transforma o corpo de uma resposta SSE numa sequência de eventos tipados.
 *
 * O buffer existe porque **um chunk da rede não é um quadro**: ele pode conter
 * três quadros, meio quadro, ou terminar no meio de um caractere multibyte — daí
 * o `TextDecoder` em modo `stream`, sem o qual um "ç" partido em dois chunks
 * viraria lixo na tela.
 *
 * Quem consome pode desistir no meio (`break`, cancelamento): o `finally`
 * cancela a leitura e é isso que fecha a conexão com o servidor.
 */
export async function* parseChatStream(response: Response): AsyncGenerator<ChatStreamEvent> {
  const body = response.body
  if (!body) {
    throw new ApiError('erro_interno', 'A resposta do servidor veio sem conteúdo.', null)
  }

  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const event = parseFrame(frame)
        if (event) {
          yield event
        }
        boundary = buffer.indexOf('\n\n')
      }
    }

    // Conexão fechada sem o `\n\n` final: o último quadro ainda vale.
    const last = parseFrame(buffer)
    if (last) {
      yield last
    }
  } finally {
    await reader.cancel().catch(() => undefined)
  }
}
