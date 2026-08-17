// @vitest-environment jsdom
import { StrictMode } from 'react'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatView } from '@/components/ChatView'
import { ApiError } from '@/lib/api'
import type { ChatStreamEvent } from '@/lib/sse'
import type { DocumentDetail } from '@/lib/types'

vi.mock('@/lib/api', async () => {
  const real = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...real, createConversation: vi.fn(), listMessages: vi.fn(), openChatStream: vi.fn() }
})

// O parser de SSE tem testes próprios em `lib/sse.test.ts`; aqui ele é
// substituído por um canal que o teste alimenta evento a evento, que é o que
// permite observar a resposta aparecendo aos poucos.
vi.mock('@/lib/sse', () => ({ parseChatStream: vi.fn() }))

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

const { createConversation, listMessages, openChatStream } = await import('@/lib/api')
const { parseChatStream } = await import('@/lib/sse')
const { toast } = await import('sonner')
const createConversationMock = vi.mocked(createConversation)
const listMessagesMock = vi.mocked(listMessages)
const openChatStreamMock = vi.mocked(openChatStream)
const parseChatStreamMock = vi.mocked(parseChatStream)
const toastErrorMock = vi.mocked(toast.error)
const toastInfoMock = vi.mocked(toast.info)

// O `ScrollArea` do Radix usa `ResizeObserver` para decidir quando mostrar a
// barra, e o jsdom não o implementa. O dublê existe por causa do ambiente de
// teste; no navegador a API é nativa.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub)

const DOCUMENT: DocumentDetail = {
  id: 'doc-1',
  filename: 'Exemplo-YAITEC.pdf',
  status: 'ready',
  page_count: 4,
  chunks_total: 10,
  chunks_processed: 10,
  error_message: null,
}

function campo(): HTMLTextAreaElement {
  return screen.getByLabelText('Sua pergunta sobre o documento') as HTMLTextAreaElement
}

/**
 * Canal de eventos que o teste controla, no lugar do stream real.
 *
 * O `abort` rejeita a espera do jeito que o cancelamento de um `fetch` faz —
 * sem isso o cancelamento pareceria funcionar num teste em que nada acontece.
 */
function eventChannel() {
  const queue: ChatStreamEvent[] = []
  let wake: (() => void) | null = null
  let closed = false

  return {
    push(event: ChatStreamEvent) {
      queue.push(event)
      wake?.()
      wake = null
    },
    close() {
      closed = true
      wake?.()
      wake = null
    },
    async *iterate(signal: AbortSignal): AsyncGenerator<ChatStreamEvent> {
      for (;;) {
        while (queue.length > 0) {
          yield queue.shift() as ChatStreamEvent
        }
        if (closed) {
          return
        }
        await new Promise<void>((resolve, reject) => {
          wake = resolve
          signal.addEventListener('abort', () => reject(signal.reason as Error), { once: true })
        })
      }
    },
  }
}

/** Liga o canal ao `useChat`, devolvendo o canal para o teste alimentar. */
function ligarStream() {
  const channel = eventChannel()
  let signal: AbortSignal | null = null
  openChatStreamMock.mockImplementation((_conversationId, _question, aborted) => {
    signal = aborted
    return Promise.resolve({} as Response)
  })
  parseChatStreamMock.mockImplementation(() => channel.iterate(signal as AbortSignal))
  return channel
}

async function perguntar(texto: string) {
  await userEvent.click(campo())
  await userEvent.keyboard(`${texto}{Enter}`)
}

describe('ChatView', () => {
  beforeEach(() => {
    localStorage.clear()
    createConversationMock.mockReset()
    createConversationMock.mockResolvedValue({ id: 'conv-1' })
    listMessagesMock.mockReset()
    listMessagesMock.mockResolvedValue([])
    openChatStreamMock.mockReset()
    openChatStreamMock.mockResolvedValue({} as Response)
    parseChatStreamMock.mockReset()
    // Stream que fecha sem dizer nada: o padrão para os testes que não são
    // sobre a resposta.
    parseChatStreamMock.mockImplementation(async function* () {})
    toastErrorMock.mockReset()
    toastInfoMock.mockReset()
  })

  afterEach(cleanup)

  it('cria a conversa uma única vez ao entrar no chat e habilita o campo', async () => {
    // O modo estrito executa o efeito duas vezes de propósito: é exatamente o
    // cenário que criaria uma conversa sobrando a cada montagem.
    render(
      <StrictMode>
        <ChatView document={DOCUMENT} onReset={vi.fn()} />
      </StrictMode>,
    )

    await waitFor(() => expect(campo().disabled).toBe(false))
    expect(createConversationMock).toHaveBeenCalledTimes(1)
    expect(createConversationMock).toHaveBeenCalledWith('doc-1')
  })

  it('reaproveita a conversa guardada do mesmo documento, sem criar outra', async () => {
    localStorage.setItem(
      'talkdoc:conversation',
      JSON.stringify({ documentId: 'doc-1', conversationId: 'conv-guardada' }),
    )

    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)

    await waitFor(() => expect(campo().disabled).toBe(false))
    expect(createConversationMock).not.toHaveBeenCalled()
  })

  it('ignora a conversa guardada de outro documento', async () => {
    localStorage.setItem(
      'talkdoc:conversation',
      JSON.stringify({ documentId: 'outro-doc', conversationId: 'conv-antiga' }),
    )

    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)

    await waitFor(() => expect(createConversationMock).toHaveBeenCalledWith('doc-1'))
  })

  it('mantém o campo fora do ar e avisa quando a conversa não pôde ser criada', async () => {
    createConversationMock.mockRejectedValue(
      new ApiError('documento_nao_pronto', 'O documento ainda está sendo lido.', 409),
    )

    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)

    // Documento ainda em leitura é estado transitório, não falha: sai como
    // aviso neutro, pelo canal que a severidade do mapa escolhe.
    await waitFor(() => expect(toastInfoMock).toHaveBeenCalled())
    expect(toastInfoMock.mock.calls[0]?.[0]).toBe('Documento ainda não está pronto')
    expect(toastErrorMock).not.toHaveBeenCalled()
    expect(campo().disabled).toBe(true)
  })

  it('envia com Enter e quebra linha com Shift+Enter', async () => {
    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)
    await waitFor(() => expect(campo().disabled).toBe(false))

    await userEvent.click(campo())
    await userEvent.keyboard('primeira linha{Shift>}{Enter}{/Shift}segunda linha')

    expect(campo().value).toBe('primeira linha\nsegunda linha')

    await userEvent.keyboard('{Enter}')

    expect(campo().value).toBe('')
    expect(screen.getByText(/primeira linha/)).toBeTruthy()
  })

  it('não envia pergunta em branco', async () => {
    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)
    await waitFor(() => expect(campo().disabled).toBe(false))

    const enviar = screen.getByRole('button', { name: 'Enviar pergunta' })
    expect(enviar).toHaveProperty('disabled', true)

    await userEvent.click(campo())
    await userEvent.keyboard('   {Enter}')

    expect(within(screen.getByRole('list', { name: 'Conversa' })).queryAllByRole('listitem')).toHaveLength(0)
  })

  it('mostra "pensando" e depois a resposta chegando aos poucos', async () => {
    const canal = ligarStream()
    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)
    await waitFor(() => expect(campo().disabled).toBe(false))

    await perguntar('quais serviços a YAITEC oferece?')

    expect(await screen.findByText('Pensando na resposta.')).toBeTruthy()
    expect(openChatStreamMock).toHaveBeenCalledWith(
      'conv-1',
      'quais serviços a YAITEC oferece?',
      expect.any(AbortSignal),
    )

    canal.push({ type: 'token', text: 'A YAITEC ' })
    expect(await screen.findByText('A YAITEC')).toBeTruthy()
    // O "pensando" some no primeiro token, não no fim da resposta.
    expect(screen.queryByText('Pensando na resposta.')).toBeNull()

    canal.push({ type: 'token', text: 'oferece consultoria.' })
    expect(await screen.findByText('A YAITEC oferece consultoria.')).toBeTruthy()

    canal.push({ type: 'done', messageId: 12, truncated: false })
    canal.close()

    await waitFor(() => expect(campo().disabled).toBe(false))
    expect(screen.getByText('A YAITEC oferece consultoria.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Parar resposta/ })).toBeNull()
  })

  it('cancela a resposta em andamento, preservando o que já chegou', async () => {
    const canal = ligarStream()
    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)
    await waitFor(() => expect(campo().disabled).toBe(false))

    await perguntar('resuma o documento')
    canal.push({ type: 'token', text: 'Começo da resposta' })
    await screen.findByText('Começo da resposta')

    await userEvent.click(screen.getByRole('button', { name: /Parar resposta/ }))

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Parar resposta/ })).toBeNull(),
    )
    expect(screen.getByText('Começo da resposta')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Enviar pergunta' })).toBeTruthy()
    expect(toastErrorMock).not.toHaveBeenCalled()
  })

  it('trata erro antes do primeiro evento como aviso, sem resposta pela metade', async () => {
    openChatStreamMock.mockRejectedValue(
      new ApiError('limite_de_uso', 'O provedor recusou por enquanto.', 429),
    )
    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)
    await waitFor(() => expect(campo().disabled).toBe(false))

    await perguntar('qual o endereço?')

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled())
    expect(toastErrorMock.mock.calls[0]?.[0]).toBe('Limite de uso atingido')
    expect(parseChatStreamMock).not.toHaveBeenCalled()
    // Só a pergunta ficou na lista: não há resposta vazia fingindo existir.
    expect(within(screen.getByRole('list', { name: 'Conversa' })).getAllByRole('listitem')).toHaveLength(1)
    await waitFor(() => expect(campo().disabled).toBe(false))
  })

  it('trata erro no meio do stream preservando o texto recebido', async () => {
    const canal = ligarStream()
    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)
    await waitFor(() => expect(campo().disabled).toBe(false))

    await perguntar('e quanto a isso?')
    canal.push({ type: 'token', text: 'Metade da resposta' })
    await screen.findByText('Metade da resposta')

    canal.push({ type: 'error', code: 'provedor', message: 'O provedor falhou.' })
    canal.close()

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled())
    expect(screen.getByText('Metade da resposta')).toBeTruthy()
  })

  it('devolve a pergunta ao campo e oferece repetir quando o envio falha', async () => {
    openChatStreamMock.mockRejectedValue(
      new ApiError('limite_de_uso', 'O provedor recusou por enquanto.', 429),
    )
    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)
    await waitFor(() => expect(campo().disabled).toBe(false))

    await perguntar('qual o e-mail de contato?')

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled())
    // A pergunta digitada não se perde: ela volta para o campo.
    await waitFor(() => expect(campo().value).toBe('qual o e-mail de contato?'))

    const aviso = toastErrorMock.mock.calls[0]?.[1] as
      | { action?: { label: string; onClick: () => void } }
      | undefined
    expect(aviso?.action?.label).toBe('Tentar de novo')

    openChatStreamMock.mockClear()
    const canal = ligarStream()
    aviso?.action?.onClick()

    await waitFor(() =>
      expect(openChatStreamMock).toHaveBeenCalledWith(
        'conv-1',
        'qual o e-mail de contato?',
        expect.any(AbortSignal),
      ),
    )
    // Repetido o envio, o campo volta a ficar limpo.
    await waitFor(() => expect(campo().value).toBe(''))
    canal.close()
  })

  it('exibe a recusa como resposta do assistente, sem aviso de erro', async () => {
    const canal = ligarStream()
    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)
    await waitFor(() => expect(campo().disabled).toBe(false))

    await perguntar('qual a cotação do dólar?')
    canal.push({ type: 'token', text: 'Não encontrei isso no documento.' })
    canal.push({ type: 'citations', citations: [] })
    canal.push({ type: 'done', messageId: 9, truncated: false })
    canal.close()

    expect(await screen.findByText('sem base no documento')).toBeTruthy()
    expect(screen.getByText('Não encontrei isso no documento.')).toBeTruthy()
    expect(toastErrorMock).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /ver trecho/ })).toBeNull()
  })

  it('restaura o histórico da conversa guardada, sem criar outra', async () => {
    localStorage.setItem(
      'talkdoc:conversation',
      JSON.stringify({ documentId: 'doc-1', conversationId: 'conv-guardada' }),
    )
    listMessagesMock.mockResolvedValue([
      {
        id: 1,
        role: 'user',
        content: 'quais serviços a YAITEC oferece?',
        citations: [],
        truncated: false,
        created_at: '2026-08-17T12:00:00Z',
      },
      {
        id: 2,
        role: 'assistant',
        content: 'Consultoria e engenharia de dados.',
        citations: [{ page_number: 3, snippet: 'trecho', chunk_index: 1, score: 0.9 }],
        truncated: false,
        created_at: '2026-08-17T12:00:05Z',
      },
    ])

    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)

    expect(await screen.findByText('Consultoria e engenharia de dados.')).toBeTruthy()
    expect(screen.getByText('quais serviços a YAITEC oferece?')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'ver trecho da página 3' })).toBeTruthy()
    expect(listMessagesMock).toHaveBeenCalledWith('conv-guardada')
    expect(createConversationMock).not.toHaveBeenCalled()
  })

  it('parte de uma pergunta sugerida quando a conversa está vazia', async () => {
    const canal = ligarStream()
    render(<ChatView document={DOCUMENT} onReset={vi.fn()} />)
    await waitFor(() => expect(campo().disabled).toBe(false))

    await userEvent.click(screen.getByRole('button', { name: 'Do que trata este documento?' }))

    await waitFor(() =>
      expect(openChatStreamMock).toHaveBeenCalledWith(
        'conv-1',
        'Do que trata este documento?',
        expect.any(AbortSignal),
      ),
    )
    canal.close()
  })

  it('mostra o nome do documento e o caminho de volta para o envio', async () => {
    const onReset = vi.fn()
    render(<ChatView document={DOCUMENT} onReset={onReset} />)

    expect(screen.getByText(/Exemplo-YAITEC\.pdf/)).toBeTruthy()

    await userEvent.click(screen.getByRole('button', { name: 'Enviar outro documento' }))
    expect(onReset).toHaveBeenCalledTimes(1)
  })
})
