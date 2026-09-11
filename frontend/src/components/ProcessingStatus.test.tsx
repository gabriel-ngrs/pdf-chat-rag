// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ProcessingStatus } from '@/components/ProcessingStatus'
import { useDocumentStatus } from '@/hooks/useDocumentStatus'
import type { DocumentDetail } from '@/lib/types'

vi.mock('@/hooks/useDocumentStatus', async () => {
  const actual = await vi.importActual<typeof import('@/hooks/useDocumentStatus')>(
    '@/hooks/useDocumentStatus',
  )
  return { ...actual, useDocumentStatus: vi.fn() }
})

vi.mock('@/hooks/useReducedMotion', () => ({ useReducedMotion: () => true }))

const useDocumentStatusMock = vi.mocked(useDocumentStatus)

function documento(): DocumentDetail {
  return {
    id: 'doc-1',
    filename: 'lgpd-capitulos-1-2.pdf',
    status: 'processing',
    page_count: 3,
    chunks_total: 10,
    chunks_processed: 0,
    error_message: null,
  }
}

describe('ProcessingStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    useDocumentStatusMock.mockReturnValue({ document: documento(), missing: false, loading: false })
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('mostra avanço estimado enquanto um documento pequeno ainda aguarda o primeiro lote', async () => {
    render(<ProcessingStatus documentId="doc-1" onReset={vi.fn()} />)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })

    const progress = screen.getByRole('progressbar', { name: 'Progresso da leitura do documento' })
    expect(Number(progress.getAttribute('aria-valuenow'))).toBeGreaterThan(0)
    expect(progress.getAttribute('aria-valuetext')).toMatch(/estimado/i)
    expect(screen.getByText(/Preparando a leitura/)).toBeTruthy()
  })

  it('mantém o progresso confirmado em documentos que exigem vários lotes', async () => {
    useDocumentStatusMock.mockReturnValue({
      document: { ...documento(), chunks_total: 17 },
      missing: false,
      loading: false,
    })
    render(<ProcessingStatus documentId="doc-1" onReset={vi.fn()} />)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })

    const progress = screen.getByRole('progressbar', { name: 'Progresso da leitura do documento' })
    expect(progress.getAttribute('aria-valuenow')).toBe('0')
    expect(progress.getAttribute('aria-valuetext')).toBe('0 de 17 trechos')
  })
})
