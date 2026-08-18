// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Markdown } from '@/components/Markdown'

/**
 * Os critérios de aceite da MELH-001 que moram no renderizador.
 *
 * O que a melhoria pede é verificável sem navegador: a sintaxe some da tela e
 * vira elemento, e HTML vindo do documento nunca chega a ser elemento nenhum.
 */
describe('Markdown', () => {
  afterEach(cleanup)

  it('renderiza negrito e lista sem deixar nenhum asterisco na tela', () => {
    const { container } = render(
      <Markdown>{'Resumo do documento.\n\n*   **Estratégia:** define formatos.\n*   **Diretrizes:** proíbe citar.'}</Markdown>,
    )

    expect(container.textContent).not.toContain('*')
    expect(container.querySelectorAll('li')).toHaveLength(2)
    expect(screen.getByText('Estratégia:').tagName).toBe('STRONG')
  })

  it('mostra HTML do documento como texto, e nunca como elemento', () => {
    const { container } = render(
      <Markdown>{'Use a tag <script>alert(1)</script> com cuidado.'}</Markdown>,
    )

    // O conteúdo vem de um modelo que leu um PDF de origem desconhecida: esta
    // é a asserção que impede a melhoria de virar um XSS.
    expect(container.querySelector('script')).toBeNull()
    expect(container.innerHTML).not.toContain('<script')
    expect(container.textContent).toContain('<script>alert(1)</script>')
  })

  it('não deixa uma imagem do documento virar requisição do navegador', () => {
    const { container } = render(
      <Markdown>{'![nada](https://exemplo.invalido/pixel.png)'}</Markdown>,
    )

    expect(container.querySelector('img')).toBeNull()
  })

  it('abre link em nova aba sem entregar o referrer', () => {
    render(<Markdown>{'Veja o [site](https://exemplo.invalido).'}</Markdown>)

    const link = screen.getByRole('link', { name: 'site' })
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toBe('noreferrer')
  })

  it('rebaixa título a texto forte, para não entrar na árvore de cabeçalhos', () => {
    const { container } = render(<Markdown>{'## Pontos principais\n\nTexto.'}</Markdown>)

    expect(container.querySelector('h1, h2, h3, h4, h5, h6')).toBeNull()
    expect(screen.getByText('Pontos principais').tagName).toBe('P')
  })

  it('deixa a tabela rolar dentro do próprio contêiner', () => {
    const { container } = render(
      <Markdown>{'| a | b |\n| --- | --- |\n| 1 | 2 |'}</Markdown>,
    )

    const table = container.querySelector('table')
    expect(table).not.toBeNull()
    expect(table?.parentElement?.className).toContain('overflow-x-auto')
  })
})
