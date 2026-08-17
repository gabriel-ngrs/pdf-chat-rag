// @vitest-environment jsdom
import { StrictMode } from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatView } from '@/components/ChatView'
import { ApiError } from '@/lib/api'
import type { DocumentDetail } from '@/lib/types'

vi.mock('@/lib/api', async () => {
  const real = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...real, createConversation: vi.fn(), listMessages: vi.fn() }
})

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

const { createConversation } = await import('@/lib/api')
const { toast } = await import('sonner')
const createConversationMock = vi.mocked(createConversation)
const toastErrorMock = vi.mocked(toast.error)

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

describe('ChatView', () => {
  beforeEach(() => {
    localStorage.clear()
    createConversationMock.mockReset()
    createConversationMock.mockResolvedValue({ id: 'conv-1' })
    toastErrorMock.mockReset()
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

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled())
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

    expect(screen.queryByRole('listitem')).toBeNull()
  })

  it('mostra o nome do documento e o caminho de volta para o envio', async () => {
    const onReset = vi.fn()
    render(<ChatView document={DOCUMENT} onReset={onReset} />)

    expect(screen.getByText(/Exemplo-YAITEC\.pdf/)).toBeTruthy()

    await userEvent.click(screen.getByRole('button', { name: 'Enviar outro documento' }))
    expect(onReset).toHaveBeenCalledTimes(1)
  })
})
