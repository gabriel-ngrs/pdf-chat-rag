// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import { CitationChip } from '@/components/CitationChip'
import type { Citation } from '@/lib/types'

const CITATION: Citation = {
  page_number: 4,
  snippet: 'A YAITEC atua com engenharia de dados e inteligência artificial aplicada.',
  chunk_index: 7,
  score: 0.834,
}

describe('CitationChip', () => {
  afterEach(cleanup)

  it('é alcançável por Tab e revela trecho e página ao ser acionado', async () => {
    render(<CitationChip citation={CITATION} />)

    await userEvent.tab()
    const chip = screen.getByRole('button', { name: 'ver trecho da página 4' })
    expect(document.activeElement).toBe(chip)

    await userEvent.keyboard('{Enter}')

    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByText('Página 4')).toBeTruthy()
    expect(screen.getByText(CITATION.snippet)).toBeTruthy()
  })

  it('mostra o trecho exatamente como o servidor mandou, sem recortar de novo', async () => {
    const longo = 'a'.repeat(237) + ' fim'
    render(<CitationChip citation={{ ...CITATION, snippet: longo }} />)

    await userEvent.click(screen.getByRole('button', { name: /ver trecho/ }))

    expect(screen.getByText(longo).textContent).toBe(longo)
  })

  it('mostra a similaridade de forma discreta, só dentro do diálogo', async () => {
    render(<CitationChip citation={CITATION} />)

    expect(screen.queryByText(/similaridade/)).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: /ver trecho/ }))

    expect(screen.getByText('similaridade 0,83')).toBeTruthy()
  })

  it('rotula a página no chip para quem lê a tela e para quem a ouve', () => {
    render(<CitationChip citation={CITATION} />)

    const chip = screen.getByRole('button', { name: 'ver trecho da página 4' })
    expect(chip.textContent).toContain('página 4')
  })
})
