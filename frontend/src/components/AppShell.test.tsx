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

  it('assina a marca com a logo da Yaitec, sem tirar o TalkDoc do primeiro plano', () => {
    render(<AppShell>conteúdo</AppShell>)

    expect(screen.getByText('Talk')).toBeTruthy()

    const logo = screen.getByRole('link', { name: /por Yaitec/ })
    expect(logo.getAttribute('href')).toBe('https://yaitec.com')
    expect(logo.getAttribute('target')).toBe('_blank')
    expect(logo.getAttribute('rel')).toBe('noreferrer')

    // A logo é desenho, não texto: o nome acessível vem do link, e o `svg` não
    // pode anunciar a mesma coisa uma segunda vez.
    const marca = logo.querySelector('svg')
    expect(marca?.getAttribute('aria-hidden')).toBe('true')
  })

  it('mantém o cabeçalho na altura de sempre depois de ganhar a segunda marca', () => {
    const { container } = render(<AppShell>conteúdo</AppShell>)

    // `h-14` é o que sustenta a proporção do cabeçalho contra o conteúdo. A
    // logo entrou menor que o wordmark justamente para não empurrar isto.
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
