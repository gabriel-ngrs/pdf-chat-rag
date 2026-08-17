// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MessageList, isNearBottom } from '@/components/MessageList'
import type { ChatMessage } from '@/lib/types'

// O `ScrollArea` do Radix usa `ResizeObserver` para decidir quando mostrar a
// barra, e o jsdom não o implementa. O dublê existe por causa do ambiente de
// teste; no navegador a API é nativa.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub)

function message(overrides: Partial<ChatMessage> & Pick<ChatMessage, 'id' | 'role'>): ChatMessage {
  return {
    content: 'conteúdo',
    citations: [],
    truncated: false,
    created_at: '2026-08-17T12:00:00Z',
    ...overrides,
  }
}

describe('MessageList', () => {
  afterEach(cleanup)

  it('renderiza o histórico na ordem em que veio', () => {
    render(
      <MessageList
        messages={[
          message({ id: 1, role: 'user', content: 'quais serviços a YAITEC oferece?' }),
          message({ id: 2, role: 'assistant', content: 'Consultoria e engenharia de dados.' }),
          message({ id: 3, role: 'user', content: 'e quanto a isso?' }),
        ]}
      />,
    )

    const itens = screen.getAllByRole('listitem').map((item) => item.textContent)
    expect(itens).toHaveLength(3)
    expect(itens[0]).toContain('quais serviços a YAITEC oferece?')
    expect(itens[1]).toContain('Consultoria e engenharia de dados.')
    expect(itens[2]).toContain('e quanto a isso?')
  })

  it('anuncia mensagens novas numa região viva presente desde o início', () => {
    const { rerender } = render(<MessageList messages={[]} />)

    const lista = screen.getByRole('list')
    expect(lista.getAttribute('aria-live')).toBe('polite')

    rerender(<MessageList messages={[message({ id: 1, role: 'assistant' })]} />)

    // A mesma região do primeiro render: recriá-la faria a primeira resposta
    // passar em silêncio para quem usa leitor de tela.
    expect(screen.getByRole('list')).toBe(lista)
  })

  it('lista as citações da resposta ordenadas por página', () => {
    render(
      <MessageList
        messages={[
          message({
            id: 1,
            role: 'assistant',
            content: 'A YAITEC oferece consultoria.',
            citations: [
              { page_number: 7, snippet: 'depois', chunk_index: 12, score: 0.71 },
              { page_number: 2, snippet: 'antes', chunk_index: 3, score: 0.88 },
            ],
          }),
        ]}
      />,
    )

    const chips = screen.getAllByRole('button', { name: /ver trecho da página/ })
    expect(chips.map((chip) => chip.textContent)).toEqual(['página 2', 'página 7'])
  })

  it('não desenha área de citação quando a resposta não tem nenhuma', () => {
    render(
      <MessageList
        messages={[
          message({ id: 1, role: 'assistant', content: 'Não encontrei isso no documento.' }),
        ]}
      />,
    )

    expect(screen.queryByRole('button', { name: /ver trecho/ })).toBeNull()
    expect(screen.queryByLabelText('Trechos que fundamentam a resposta')).toBeNull()
  })

  it('mostra a recusa como resposta legítima, com marca sutil e sem cara de erro', () => {
    render(
      <MessageList
        messages={[
          message({
            id: 1,
            role: 'assistant',
            content: 'Não encontrei isso no documento.',
          }),
        ]}
      />,
    )

    expect(screen.getByText('Não encontrei isso no documento.')).toBeTruthy()
    expect(screen.getByText('sem base no documento')).toBeTruthy()
    // Recusa não é falha: nada de alerta, nada de "interrompida".
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText(/interrompida/)).toBeNull()
  })

  it('marca a resposta interrompida sem confundi-la com recusa', () => {
    render(
      <MessageList
        messages={[
          message({
            id: 1,
            role: 'assistant',
            content: 'Metade da resposta',
            truncated: true,
          }),
        ]}
      />,
    )

    expect(screen.getByText('Resposta interrompida antes do fim.')).toBeTruthy()
    expect(screen.queryByText('sem base no documento')).toBeNull()
  })

  it('mostra o estado inicial só enquanto não há mensagem', () => {
    const { rerender } = render(
      <MessageList messages={[]} emptyState={<p>Pergunte alguma coisa</p>} />,
    )

    expect(screen.getByText('Pergunte alguma coisa')).toBeTruthy()

    rerender(
      <MessageList
        messages={[message({ id: 1, role: 'user', content: 'olá' })]}
        emptyState={<p>Pergunte alguma coisa</p>}
      />,
    )

    expect(screen.queryByText('Pergunte alguma coisa')).toBeNull()
  })

  it('diferencia quem falou também para quem não vê a tela', () => {
    render(
      <MessageList
        messages={[
          message({ id: 1, role: 'user', content: 'qual o endereço?' }),
          message({ id: 2, role: 'assistant', content: 'Rua Exemplo, 100.' }),
        ]}
      />,
    )

    expect(screen.getByText('Você perguntou:')).toBeTruthy()
    expect(screen.getByText('O TalkDoc respondeu:')).toBeTruthy()
  })
})

/**
 * A regra que decide se a conversa continua acompanhando o fim.
 *
 * Testada aqui, e não pela tela: o jsdom não calcula layout, e `scrollHeight`
 * é sempre zero — pela tela, a asserção seria sobre o ambiente de teste.
 */
describe('isNearBottom', () => {
  it('acompanha quem está no fim exato da lista', () => {
    expect(isNearBottom(1000, 600, 400)).toBe(true)
  })

  it('tolera a folga de alguns pixels acima do fim', () => {
    expect(isNearBottom(1000, 560, 400)).toBe(true)
  })

  it('para de acompanhar quem subiu para reler', () => {
    expect(isNearBottom(1000, 300, 400)).toBe(false)
  })
})
