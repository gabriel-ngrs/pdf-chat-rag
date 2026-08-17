// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Progress } from '@/components/ui/progress'

/**
 * Regressão: o componente já desestruturou `value` e o usou só no `transform`
 * do indicador, sem repassá-lo à Root. A barra desenhava certo e ficava muda
 * para leitor de tela, com `data-state` travado em "indeterminate" — defeito
 * invisível a olho nu, e o tipo de coisa que só um teste segura.
 */
describe('Progress', () => {
  afterEach(cleanup)

  it('expõe o valor ao leitor de tela, não só ao pixel', () => {
    render(<Progress value={40} aria-label="Progresso da leitura" />)

    const barra = screen.getByRole('progressbar', { name: 'Progresso da leitura' })
    expect(barra.getAttribute('aria-valuenow')).toBe('40')
    expect(barra.getAttribute('aria-valuemax')).toBe('100')
    expect(barra.getAttribute('data-value')).toBe('40')
  })

  it('distingue em progresso, completo e indeterminado no data-state', () => {
    const { rerender } = render(<Progress value={40} aria-label="p" />)
    expect(screen.getByRole('progressbar').getAttribute('data-state')).toBe('loading')

    rerender(<Progress value={100} aria-label="p" />)
    expect(screen.getByRole('progressbar').getAttribute('data-state')).toBe('complete')

    rerender(<Progress aria-label="p" />)
    const indeterminado = screen.getByRole('progressbar')
    expect(indeterminado.getAttribute('data-state')).toBe('indeterminate')
    expect(indeterminado.getAttribute('aria-valuenow')).toBe(null)
  })

  it('desenha o indicador na proporção do valor', () => {
    const { container } = render(<Progress value={25} aria-label="p" />)

    const indicador = container.querySelector<HTMLElement>('[data-slot="progress-indicator"]')
    expect(indicador?.style.transform).toBe('translateX(-75%)')
  })
})
