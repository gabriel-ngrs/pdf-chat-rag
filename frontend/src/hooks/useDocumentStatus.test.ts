// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { progressPercent, useDocumentStatus } from '@/hooks/useDocumentStatus'
import { ApiError } from '@/lib/api'
import type { DocumentDetail } from '@/lib/types'

vi.mock('@/lib/api', async () => {
  const real = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...real, fetchDocument: vi.fn() }
})

const { fetchDocument } = await import('@/lib/api')
const fetchDocumentMock = vi.mocked(fetchDocument)

function documento(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    id: 'doc-1',
    filename: 'contrato.pdf',
    status: 'processing',
    page_count: 3,
    chunks_total: 10,
    chunks_processed: 0,
    error_message: null,
    ...overrides,
  }
}

describe('progressPercent', () => {
  it('não inventa progresso enquanto o total de trechos é desconhecido', () => {
    expect(progressPercent(documento({ chunks_total: null }))).toBe(null)
    expect(progressPercent(null)).toBe(null)
  })

  it('não inventa progresso quando o documento tem zero trechos', () => {
    expect(progressPercent(documento({ chunks_total: 0 }))).toBe(null)
  })

  it('deriva a porcentagem do que o backend informou', () => {
    expect(progressPercent(documento({ chunks_processed: 0 }))).toBe(0)
    expect(progressPercent(documento({ chunks_processed: 3 }))).toBe(30)
    expect(progressPercent(documento({ chunks_processed: 10 }))).toBe(100)
  })

  it('nunca passa de 100, mesmo se o servidor contar a mais', () => {
    expect(progressPercent(documento({ chunks_processed: 14 }))).toBe(100)
  })
})

describe('useDocumentStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    fetchDocumentMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  /**
   * Avança o relógio falso deixando as promessas pendentes resolverem.
   *
   * O `act` é obrigatório: as atualizações de estado saem de dentro de uma
   * promessa, e sem ele o React não as aplica antes da asserção.
   */
  async function avancar(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms)
    })
  }

  it('para de consultar depois que o documento fica pronto', async () => {
    fetchDocumentMock
      .mockResolvedValueOnce(documento({ status: 'processing', chunks_processed: 5 }))
      .mockResolvedValueOnce(documento({ status: 'ready', chunks_processed: 10 }))

    const { result } = renderHook(() => useDocumentStatus('doc-1'))

    await avancar(0)
    expect(fetchDocumentMock).toHaveBeenCalledTimes(1)

    await avancar(1_500)
    expect(result.current.document?.status).toBe('ready')

    // Estado terminal não muda mais: continuar perguntando só gasta requisição.
    await avancar(10_000)
    expect(fetchDocumentMock).toHaveBeenCalledTimes(2)
  })

  it('para de consultar quando o documento falha', async () => {
    fetchDocumentMock.mockResolvedValue(
      documento({ status: 'failed', error_message: 'PDF sem texto extraível.' }),
    )

    const { result } = renderHook(() => useDocumentStatus('doc-1'))

    await avancar(0)
    expect(result.current.document?.error_message).toBe('PDF sem texto extraível.')

    await avancar(10_000)
    expect(fetchDocumentMock).toHaveBeenCalledTimes(1)
  })

  it('trata documento inexistente como terminal e não reagenda', async () => {
    fetchDocumentMock.mockRejectedValue(new ApiError('nao_encontrado', 'sumiu', 404))

    const { result } = renderHook(() => useDocumentStatus('doc-1'))

    await avancar(0)
    expect(result.current.missing).toBe(true)

    await avancar(10_000)
    expect(fetchDocumentMock).toHaveBeenCalledTimes(1)
  })

  it('mantém o último estado conhecido quando a rede falha, e tenta de novo', async () => {
    fetchDocumentMock
      .mockResolvedValueOnce(documento({ chunks_processed: 4 }))
      .mockRejectedValueOnce(new ApiError('rede_indisponivel', 'sem resposta', null))
      .mockResolvedValueOnce(documento({ status: 'ready', chunks_processed: 10 }))

    const { result } = renderHook(() => useDocumentStatus('doc-1'))

    await avancar(0)
    expect(result.current.document?.chunks_processed).toBe(4)

    await avancar(1_500)
    // A falha não apagou o que já se sabia.
    expect(result.current.document?.chunks_processed).toBe(4)
    expect(result.current.missing).toBe(false)

    await avancar(1_500)
    expect(result.current.document?.status).toBe('ready')
  })

  it('não deixa timer órfão depois de desmontar', async () => {
    fetchDocumentMock.mockResolvedValue(documento())

    const { unmount } = renderHook(() => useDocumentStatus('doc-1'))
    await avancar(0)
    expect(fetchDocumentMock).toHaveBeenCalledTimes(1)

    unmount()
    await avancar(30_000)
    expect(fetchDocumentMock).toHaveBeenCalledTimes(1)
  })

  it('respeita o piso de 1 s entre consultas', async () => {
    fetchDocumentMock.mockResolvedValue(documento())

    renderHook(() => useDocumentStatus('doc-1'))
    await avancar(0)
    expect(fetchDocumentMock).toHaveBeenCalledTimes(1)

    await avancar(999)
    expect(fetchDocumentMock).toHaveBeenCalledTimes(1)
  })

  it('não consulta nada sem documento em acompanhamento', async () => {
    const { result } = renderHook(() => useDocumentStatus(null))

    await avancar(5_000)
    expect(fetchDocumentMock).not.toHaveBeenCalled()
    expect(result.current.document).toBe(null)
  })
})
