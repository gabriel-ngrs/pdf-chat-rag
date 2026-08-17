// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UploadDropzone } from '@/components/UploadDropzone'
import { ApiError } from '@/lib/api'
import type { AppConfig } from '@/lib/types'

vi.mock('@/lib/api', async () => {
  const real = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...real, uploadDocument: vi.fn() }
})

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

const { uploadDocument } = await import('@/lib/api')
const { toast } = await import('sonner')
const uploadDocumentMock = vi.mocked(uploadDocument)
const toastErrorMock = vi.mocked(toast.error)

const LIMITS: AppConfig = { max_upload_mb: 25, max_pdf_pages: 20, max_extracted_chars: 60000 }

function pdf(name = 'contrato.pdf', size = 2 * 1024 * 1024): File {
  const file = new File(['%PDF-1.7'], name, { type: 'application/pdf' })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

function campoDeArquivo(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type=file]')
  if (!input) {
    throw new Error('input de arquivo não encontrado')
  }
  return input
}

function montar(limits: AppConfig | null = LIMITS) {
  const onAccepted = vi.fn()
  render(<UploadDropzone limits={limits} onAccepted={onAccepted} />)
  return { onAccepted }
}

describe('UploadDropzone', () => {
  beforeEach(() => {
    uploadDocumentMock.mockReset()
    toastErrorMock.mockReset()
  })

  // Sem `globals: true` o auto-cleanup da testing-library não é registrado, e o
  // DOM de um teste vazaria para o seguinte.
  afterEach(cleanup)

  it('começa com o botão de enviar desabilitado e a instrução visível', () => {
    montar()

    expect(screen.getByText(/Arraste um PDF aqui ou clique para escolher/)).toBeTruthy()
    expect(screen.getByText(/PDF de até 25 MB e 20 páginas/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Enviar documento' })).toHaveProperty(
      'disabled',
      true,
    )
  })

  it('mostra nome e tamanho do arquivo escolhido pelo input', async () => {
    montar()

    await userEvent.upload(campoDeArquivo(), pdf('contrato.pdf', 3 * 1024 * 1024))

    expect(screen.getByText('contrato.pdf')).toBeTruthy()
    expect(screen.getByText('3,0 MB')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Enviar documento' })).toHaveProperty(
      'disabled',
      false,
    )
  })

  it('aceita arquivo arrastado, não só o escolhido pelo input', () => {
    montar()
    const arquivo = pdf('arrastado.pdf')

    fireEvent.drop(campoDeArquivo().closest('div')!, { dataTransfer: { files: [arquivo] } })

    expect(screen.getByText('arrastado.pdf')).toBeTruthy()
  })

  it('recusa arquivo acima do limite antes de qualquer requisição', async () => {
    montar()

    await userEvent.upload(campoDeArquivo(), pdf('grande.pdf', 31 * 1024 * 1024))

    expect(uploadDocumentMock).not.toHaveBeenCalled()
    expect(toastErrorMock).toHaveBeenCalledOnce()
    const [titulo, opcoes] = toastErrorMock.mock.calls[0]
    expect(titulo).toBe('Arquivo grande demais')
    expect(String(opcoes?.description)).toContain('31,0 MB')
    expect(String(opcoes?.description)).toContain('25 MB')
    expect(screen.queryByText('grande.pdf')).toBe(null)
  })

  it('limpa o campo depois de uma recusa, para o mesmo arquivo poder ser reescolhido', async () => {
    montar()

    await userEvent.upload(campoDeArquivo(), pdf('grande.pdf', 31 * 1024 * 1024))

    expect(campoDeArquivo().value).toBe('')
  })

  it('recusa arquivo que não é PDF', async () => {
    montar()
    const texto = new File(['oi'], 'planilha.txt', { type: 'text/plain' })

    // `applyAccept: false` porque o atributo `accept` é filtro do seletor, não
    // garantia: o usuário pode trocar o filtro para "todos os arquivos". Quem
    // precisa recusar é a validação, e é ela que este teste exercita.
    await userEvent.upload(campoDeArquivo(), texto, { applyAccept: false })

    expect(uploadDocumentMock).not.toHaveBeenCalled()
    expect(toastErrorMock.mock.calls[0][0]).toBe('Arquivo não é um PDF válido')
  })

  it('sem limites conhecidos não bloqueia por tamanho — quem recusa é o servidor', async () => {
    montar(null)
    expect(screen.getByText(/Os limites serão conferidos pelo servidor/)).toBeTruthy()

    await userEvent.upload(campoDeArquivo(), pdf('grande.pdf', 99 * 1024 * 1024))

    expect(toastErrorMock).not.toHaveBeenCalled()
    expect(screen.getByText('grande.pdf')).toBeTruthy()
  })

  it('envia e entrega o documento aceito a quem chamou', async () => {
    const { onAccepted } = montar()
    uploadDocumentMock.mockResolvedValue({ id: 'doc-1', status: 'pending' })

    await userEvent.upload(campoDeArquivo(), pdf())
    await userEvent.click(screen.getByRole('button', { name: 'Enviar documento' }))

    await waitFor(() => expect(onAccepted).toHaveBeenCalledWith({ id: 'doc-1', status: 'pending' }))
    expect(uploadDocumentMock).toHaveBeenCalledOnce()
  })

  it('durante o envio bloqueia o campo e o botão, e mostra indicador indeterminado', async () => {
    montar()
    let concluir: (valor: { id: string; status: 'pending' }) => void = () => {}
    uploadDocumentMock.mockReturnValue(
      new Promise((resolve) => {
        concluir = resolve
      }),
    )

    await userEvent.upload(campoDeArquivo(), pdf())
    await userEvent.click(screen.getByRole('button', { name: 'Enviar documento' }))

    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Enviando'))
    expect(campoDeArquivo().disabled).toBe(true)
    expect(screen.getByRole('button', { name: 'Enviar documento' })).toHaveProperty(
      'disabled',
      true,
    )

    concluir({ id: 'doc-1', status: 'pending' })
    await waitFor(() => expect(screen.queryByRole('status')).toBe(null))
  })

  it('falha do servidor vira aviso pelo código e não entrega documento nenhum', async () => {
    const { onAccepted } = montar()
    uploadDocumentMock.mockRejectedValue(new ApiError('limite_de_uso', 'quota', 429))

    await userEvent.upload(campoDeArquivo(), pdf())
    await userEvent.click(screen.getByRole('button', { name: 'Enviar documento' }))

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledOnce())
    expect(toastErrorMock.mock.calls[0][0]).toBe('Limite de uso atingido')
    expect(onAccepted).not.toHaveBeenCalled()
  })
})
