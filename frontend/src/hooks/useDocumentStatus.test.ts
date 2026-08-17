import { describe, expect, it } from 'vitest'

import { progressPercent } from '@/hooks/useDocumentStatus'
import type { DocumentDetail } from '@/lib/types'

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
