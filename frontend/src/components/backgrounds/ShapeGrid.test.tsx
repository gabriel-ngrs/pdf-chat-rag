// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ShapeGrid } from '@/components/backgrounds/ShapeGrid'

class ObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

describe('ShapeGrid', () => {
  beforeEach(() => vi.stubGlobal('ResizeObserver', ObserverStub))
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('não pede frame nenhum: a malha é estática', () => {
    const raf = vi.spyOn(window, 'requestAnimationFrame')

    render(<ShapeGrid color={[0.3, 0.35, 0.4]} />)

    // A referência do owner fazia a malha derivar a 60 fps. Este fundo fica
    // atrás da conversa — atrás do texto que a pessoa está lendo —, e por isso
    // foi portado sem laço. Sem laço, não há o que `prefers-reduced-motion`
    // reduza.
    expect(raf).not.toHaveBeenCalled()
  })

  it('atravessa a ausência de contexto 2d sem quebrar', () => {
    // O jsdom não tem canvas de verdade, e um navegador com canvas desligado
    // também não. Nos dois casos a textura simplesmente não aparece.
    const { container } = render(<ShapeGrid color={[0.3, 0.35, 0.4]} />)

    const canvas = container.querySelector('canvas')
    expect(canvas).not.toBeNull()
    expect(canvas?.getAttribute('aria-hidden')).toBe('true')
  })
})
