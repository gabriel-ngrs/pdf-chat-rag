// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

/**
 * Responde `prefers-reduced-motion` no jsdom, que não implementa `matchMedia`.
 *
 * É o que torna verificável — e não apenas inspecionável — o critério de aceite
 * da MELH-004: sob movimento reduzido nenhuma animação nova entra.
 */
function stubReducedMotion(reduced: boolean) {
  vi.stubGlobal(
    'matchMedia',
    (query: string) => ({
      matches: reduced && query.includes('prefers-reduced-motion'),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  )
}

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
  beforeEach(() => stubReducedMotion(false))
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.stubGlobal('ResizeObserver', ResizeObserverStub)
  })

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

    const chips = screen.getAllByRole('button', { name: /ver trecho consultado da página/ })
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
    expect(screen.queryByLabelText('Trechos consultados para esta resposta')).toBeNull()
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

  it('mantém os rótulos de leitor de tela fora do que se copia', () => {
    render(
      <MessageList
        messages={[
          message({ id: 1, role: 'user', content: 'qual o endereço?' }),
          message({ id: 2, role: 'assistant', content: 'Rua Exemplo, 100.' }),
        ]}
      />,
    )

    // `user-select: none` é o que tira o rótulo do `Ctrl+C` sem tirá-lo do
    // leitor de tela. O jsdom não calcula estilo, então o que dá para prender
    // é a classe — e ela é a única coisa entre o rótulo e a área de
    // transferência de quem copia uma resposta.
    for (const rotulo of ['Você perguntou:', 'O TalkDoc respondeu:']) {
      const elemento = screen.getByText(rotulo)
      const marcado = elemento.closest('.select-none')
      expect(marcado).not.toBeNull()
      // E fora do elemento que carrega o texto: selecionar só a mensagem não
      // pode pegar o rótulo nem quando a seleção começa colada nele.
      expect(elemento.textContent).not.toContain('Rua Exemplo')
      expect(elemento.textContent).not.toContain('qual o endereço')
    }
  })

  it('renderiza o Markdown da resposta pronta, sem asterisco na tela', () => {
    const { container } = render(
      <MessageList
        messages={[
          message({
            id: 1,
            role: 'assistant',
            content: 'Pontos:\n\n*   **Estratégia:** define formatos.',
          }),
        ]}
      />,
    )

    expect(container.textContent).not.toContain('*')
    expect(screen.getByText('Estratégia:').tagName).toBe('STRONG')
  })

  it('deixa a resposta em construção como texto cru, para não refluir a cada token', () => {
    render(
      <MessageList
        messages={[]}
        streaming={{ content: 'Pontos:\n\n*   **Estratég', citations: [] }}
      />,
    )

    // Markdown pela metade é Markdown inválido: passá-lo pelo parser a cada
    // token faria o parágrafo remontar sozinho enquanto a pessoa lê. O texto
    // cru aparece, e o Markdown entra quando a resposta fecha.
    expect(screen.getByText(/\*\*Estratég/)).toBeTruthy()
  })

  it('escalona a entrada dos chips de citação', () => {
    render(
      <MessageList
        messages={[
          message({
            id: 1,
            role: 'assistant',
            content: 'A YAITEC oferece consultoria.',
            citations: [
              { page_number: 2, snippet: 'antes', chunk_index: 3, score: 0.88 },
              { page_number: 7, snippet: 'depois', chunk_index: 12, score: 0.71 },
            ],
          }),
        ]}
      />,
    )

    const chips = screen
      .getAllByRole('button', { name: /ver trecho consultado da página/ })
      .map((chip) => chip.closest('li'))

    expect(chips[0]?.className).toContain('animate-rise')
    expect(chips[0]?.style.animationDelay).toBe('0ms')
    expect(chips[1]?.style.animationDelay).toBe('20ms')
  })

  it('não anima nada quando a pessoa pede movimento reduzido', () => {
    stubReducedMotion(true)

    const { container } = render(
      <MessageList
        messages={[
          message({
            id: 1,
            role: 'assistant',
            content: 'A YAITEC oferece consultoria.',
            citations: [{ page_number: 2, snippet: 'antes', chunk_index: 3, score: 0.88 }],
          }),
        ]}
      />,
    )

    // Nem classe de animação, nem atraso: sob movimento reduzido a entrada
    // escalonada não existe, em vez de existir com duração zero.
    expect(container.querySelector('.animate-rise')).toBeNull()
    expect(container.querySelector('[style*="animation-delay"]')).toBeNull()
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
