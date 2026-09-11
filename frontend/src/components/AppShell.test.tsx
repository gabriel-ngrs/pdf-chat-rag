// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AppShell } from '@/components/AppShell'

class ObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

describe('AppShell', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', ObserverStub)
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }))
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('desenha o lockup com o símbolo e o wordmark do produto', () => {
    const { container } = render(<AppShell>conteúdo</AppShell>)

    expect(screen.getByText('Talk')).toBeTruthy()
    expect(screen.getByText('Doc')).toBeTruthy()

    // O símbolo é desenho, não texto: o nome do produto já está no wordmark ao
    // lado, e o `svg` não pode anunciar a mesma coisa uma segunda vez.
    const marca = container.querySelector('header svg')
    expect(marca?.getAttribute('aria-hidden')).toBe('true')
  })

  it('não leva nenhum link para fora a partir do cabeçalho', () => {
    const { container } = render(<AppShell>conteúdo</AppShell>)

    // O único link da casca é o "pular para o conteúdo", que é âncora interna.
    const externos = [...container.querySelectorAll('a[href]')].filter(
      (a) => !a.getAttribute('href')!.startsWith('#'),
    )
    expect(externos).toHaveLength(0)
  })

  it('mantém o cabeçalho na altura de sempre com o símbolo ao lado do nome', () => {
    const { container } = render(<AppShell>conteúdo</AppShell>)

    // `h-14` é o que sustenta a proporção do cabeçalho contra o conteúdo. O
    // símbolo entrou menor que o wordmark justamente para não empurrar isto.
    expect(container.querySelector('header .h-14')).not.toBeNull()
  })

  it('só desenha camada de fundo quando a tela pede uma', () => {
    const { container, rerender } = render(<AppShell>conteúdo</AppShell>)
    expect(container.querySelector('[aria-hidden="true"].fixed')).toBeNull()

    rerender(<AppShell background="grid">conteúdo</AppShell>)
    expect(container.querySelector('[aria-hidden="true"].fixed')).not.toBeNull()
  })

  it('delimita a altura da casca para a conversa rolar dentro dela', () => {
    const { container } = render(<AppShell>conteúdo</AppShell>)

    expect(container.querySelector('.grid')?.className.split(' ')).toContain('h-dvh')
  })
})
