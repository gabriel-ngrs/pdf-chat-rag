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

/**
 * Responde `prefers-reduced-motion` e `pointer` no jsdom, que não implementa
 * `matchMedia`. É o que torna o critério de aceite da MELH-004 verificável.
 */
function stubMedia({ reduced = false, finePointer = true } = {}) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('prefers-reduced-motion')
      ? reduced
      : query.includes('pointer: fine')
        ? finePointer
        : false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

function cartao(): HTMLElement {
  const card = document.querySelector<HTMLElement>('[data-slot="card"]')
  if (!card) {
    throw new Error('card de envio não encontrado')
  }
  return card
}

describe('UploadDropzone', () => {
  beforeEach(() => {
    uploadDocumentMock.mockReset()
    toastErrorMock.mockReset()
    stubMedia()
  })

  // Sem `globals: true` o auto-cleanup da testing-library não é registrado, e o
  // DOM de um teste vazaria para o seguinte.
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

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

  it('acende o holofote onde o ponteiro está', async () => {
    montar()
    const card = cartao()

    expect(card.className).toContain('pointer-spotlight')

    fireEvent.pointerMove(card, { clientX: 120, clientY: 40 })

    // A posição viaja por custom property, e não por posição de elemento:
    // repintar um gradiente não invalida layout, mover um elemento a cada
    // `pointermove` invalidaria.
    await waitFor(() => expect(card.style.getPropertyValue('--spotlight-opacity')).toBe('1'))
    expect(card.style.getPropertyValue('--spotlight-x')).toBe('120px')

    fireEvent.pointerLeave(card)
    expect(card.style.getPropertyValue('--spotlight-opacity')).toBe('0')
  })

  it('não acende holofote nenhum sob movimento reduzido', () => {
    stubMedia({ reduced: true })
    montar()
    const card = cartao()

    expect(card.className).not.toContain('pointer-spotlight')

    fireEvent.pointerMove(card, { clientX: 120, clientY: 40 })

    // Sem a classe o `::after` não existe, e sem listener a variável nunca é
    // escrita: a animação não roda com duração zero, ela não existe.
    expect(card.style.getPropertyValue('--spotlight-opacity')).toBe('')
  })

  it('não acende holofote nenhum em ponteiro grosso', () => {
    stubMedia({ finePointer: false })
    montar()
    const card = cartao()

    fireEvent.pointerMove(card, { clientX: 120, clientY: 40 })

    // Em toque, o halo acenderia exatamente sob o dedo — no único lugar da
    // tela que o dedo está tapando.
    expect(card.style.getPropertyValue('--spotlight-opacity')).toBe('')
  })

  it('responde ao arraste por cor e escala, nunca por altura', () => {
    montar()
    const area = document.querySelector<HTMLElement>('label')
    if (!area) {
      throw new Error('área de soltar não encontrada')
    }
    const zona = area.parentElement
    if (!zona) {
      throw new Error('contêiner de arraste não encontrado')
    }

    fireEvent.dragOver(zona)

    // `transform` e cor são o que o compositor resolve sem relayout. Animar
    // altura aqui empurraria o card seguinte a cada arraste.
    expect(area.className).toContain('scale-[1.01]')
    expect(area.className).toContain('border-ring')
  })
})