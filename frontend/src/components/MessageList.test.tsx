// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { MessageList } from '@/components/MessageList'
import type { ChatMessage } from '@/lib/types'

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
