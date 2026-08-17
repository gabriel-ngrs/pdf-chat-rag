import { describe, expect, it } from 'vitest'

import { formatFileSize, validateSelection } from '@/hooks/useUpload'
import type { AppConfig } from '@/lib/types'

const LIMITS: AppConfig = { max_upload_mb: 25, max_pdf_pages: 20, max_extracted_chars: 60000 }

function fakeFile(name: string, type: string, size: number): File {
  const file = new File(['x'], name, { type })
  // `File.size` é somente-leitura; redefinir é a forma de testar o limite sem
  // alocar 26 MB de verdade.
  Object.defineProperty(file, 'size', { value: size })
  return file
}

describe('validateSelection', () => {
  it('aceita um PDF dentro do limite', () => {
    expect(validateSelection(fakeFile('contrato.pdf', 'application/pdf', 2_000_000), LIMITS)).toBe(
      null,
    )
  })

  it('recusa arquivo acima do limite antes de qualquer requisição', () => {
    const problem = validateSelection(
      fakeFile('grande.pdf', 'application/pdf', 31 * 1024 * 1024),
      LIMITS,
    )
    expect(problem?.code).toBe('arquivo_grande')
    expect(problem?.message).toContain('31,0 MB')
    expect(problem?.message).toContain('25 MB')
  })

  it('recusa arquivo que não é PDF', () => {
    expect(validateSelection(fakeFile('planilha.xlsx', 'text/plain', 1000), LIMITS)?.code).toBe(
      'arquivo_invalido',
    )
  })

  it('aceita PDF sem tipo MIME declarado pelo sistema, pela extensão', () => {
    expect(validateSelection(fakeFile('sem-tipo.PDF', '', 1000), LIMITS)).toBe(null)
  })

  it('sem limites conhecidos, não bloqueia por tamanho — quem recusa é o servidor', () => {
    expect(validateSelection(fakeFile('grande.pdf', 'application/pdf', 999_000_000), null)).toBe(
      null,
    )
  })
})

describe('formatFileSize', () => {
  it('mostra o tamanho na unidade que dá para comparar com o limite', () => {
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(2048)).toBe('2 KB')
    expect(formatFileSize(3 * 1024 * 1024)).toBe('3,0 MB')
  })
})
