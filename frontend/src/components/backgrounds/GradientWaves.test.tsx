// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GradientWaves } from '@/components/backgrounds/GradientWaves'

/**
 * O `vitest` roda em jsdom, que não tem WebGL. Nenhum teste aqui compila
 * shader: o que se verifica é a moldura em volta dele — quantos frames o
 * componente pede, e o que acontece quando o contexto gráfico não existe.
 */

const render3d = vi.fn()
const programCreated = vi.fn<(uniforms: Record<string, { value: unknown }>) => void>()
let rendererThrows = false

vi.mock('ogl', () => {
  class Renderer {
    gl: unknown
    constructor() {
      if (rendererThrows) {
        throw new Error('WebGL2 indisponível')
      }
      const canvas = document.createElement('canvas')
      this.gl = {
        canvas,
        drawingBufferWidth: 800,
        drawingBufferHeight: 600,
        clearColor: () => {},
        getExtension: () => null,
      }
    }
    setSize() {}
    render(...args: unknown[]) {
      render3d(...args)
    }
  }

  class Program {
    uniforms: Record<string, { value: unknown }>
    constructor(_gl: unknown, options: { uniforms: Record<string, { value: unknown }> }) {
      this.uniforms = options.uniforms
      programCreated(options.uniforms)
    }
  }

  return { Renderer, Program, Mesh: class {}, Triangle: class {} }
})

class ObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function stubReducedMotion(reduced: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduced && query.includes('prefers-reduced-motion'),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

const COLORS = {
  horizonColor: [0.1, 0.1, 0.12] as const,
  waveColor: [0.48, 0.65, 0.82] as const,
  crestColor: [0.67, 0.8, 0.95] as const,
  fogDepth: 45,
}

describe('GradientWaves', () => {
  beforeEach(() => {
    render3d.mockClear()
    programCreated.mockClear()
    rendererThrows = false
    vi.stubGlobal('ResizeObserver', ObserverStub)
    vi.stubGlobal('IntersectionObserver', ObserverStub)
    stubReducedMotion(false)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('não entra no laço de animação sob movimento reduzido', () => {
    stubReducedMotion(true)
    const raf = vi.spyOn(window, 'requestAnimationFrame')

    render(<GradientWaves {...COLORS} />)

    // O critério de aceite da MELH-002: um frame, e nenhum a mais. A regra do
    // `index.css` zera animação de CSS e não alcança um `requestAnimationFrame`
    // — quem precisa perguntar pela media query é este componente.
    expect(raf).not.toHaveBeenCalled()
    expect(render3d).toHaveBeenCalledTimes(1)
  })

  it('desliga o grão e o parallax junto com o movimento', () => {
    stubReducedMotion(true)
    render(<GradientWaves {...COLORS} />)

    const uniforms = programCreated.mock.calls[0][0]
    // Grão é ruído redesenhado a cada frame: congelado num frame só, viraria
    // sujeira fixa na tela. Parallax sem laço nem chegaria a ser lido — sai
    // junto porque o listener de ponteiro também não é registrado.
    expect(uniforms.uGrain.value).toBe(0)
    expect(uniforms.uEnableMouse.value).toBe(false)
  })

  it('leva as cores dos tokens para os uniforms, sem hex no componente', () => {
    render(<GradientWaves {...COLORS} />)

    const uniforms = programCreated.mock.calls[0][0]
    expect(Array.from(uniforms.uWaveColor.value as Float32Array)).toEqual(
      COLORS.waveColor.map((channel) => Math.fround(channel)),
    )
    expect(Array.from(uniforms.uCrestColor.value as Float32Array)).toEqual(
      COLORS.crestColor.map((channel) => Math.fround(channel)),
    )
  })

  it('pede frames quando o movimento é permitido', () => {
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(1)

    render(<GradientWaves {...COLORS} />)

    expect(raf).toHaveBeenCalled()
  })

  it('não derruba a árvore quando não há WebGL2', () => {
    rendererThrows = true

    const { container } = render(<GradientWaves {...COLORS} />)

    // Sem contexto gráfico o componente sai de cena em silêncio, e o gradiente
    // estático que o `AppBackground` desenha por baixo continua sendo o fundo.
    expect(container.querySelector('canvas')).toBeNull()
    expect(render3d).not.toHaveBeenCalled()
  })
})
