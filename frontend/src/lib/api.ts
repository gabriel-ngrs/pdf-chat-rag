import { getSessionId } from '@/lib/session'
import type { AppConfig, DocumentDetail, ErrorEnvelope, UploadAccepted } from '@/lib/types'

const BASE_URL = '/api'
const DEFAULT_TIMEOUT_MS = 15_000
/** Upload de até 25 MB pela rede local ainda é rápido, mas não é instantâneo. */
const UPLOAD_TIMEOUT_MS = 120_000

/**
 * Falha de requisição já traduzida para o vocabulário do envelope da §4.3.
 *
 * Carrega o `code` porque é por ele que a interface decide o que dizer; o
 * `status` fica só para diagnóstico e nunca deve virar critério de mensagem.
 */
export class ApiError extends Error {
  readonly code: string
  readonly status: number | null

  constructor(code: string, message: string, status: number | null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/**
 * Lê o envelope `{code, message}` de uma resposta de erro.
 *
 * Um proxy mal configurado responde HTML — chamar `response.json()` em cima
 * disso quebraria de forma opaca, sem nenhum código para a interface usar.
 */
async function readErrorEnvelope(response: Response): Promise<ErrorEnvelope> {
  try {
    const body: unknown = await response.json()
    if (
      typeof body === 'object' &&
      body !== null &&
      typeof (body as ErrorEnvelope).code === 'string' &&
      typeof (body as ErrorEnvelope).message === 'string'
    ) {
      return body as ErrorEnvelope
    }
  } catch {
    // Corpo não-JSON: cai no genérico abaixo.
  }
  return { code: 'erro_interno', message: 'Resposta inesperada do servidor.' }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const semResposta = () =>
    new ApiError('rede_indisponivel', 'Não foi possível falar com o servidor.', null)

  // O timeout só é desarmado quando a resposta inteira foi lida. Desarmá-lo
  // logo após os headers deixaria um corpo que nunca termina de chegar sem
  // ninguém para cortá-lo, e a promessa penduraria para sempre.
  try {
    let response: Response
    try {
      response = await fetch(`${BASE_URL}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          'X-Session-Id': getSessionId(),
          ...init.headers,
        },
      })
    } catch {
      // Rede fora, DNS, CORS ou timeout: nada disso tem envelope do servidor.
      throw semResposta()
    }

    if (!response.ok) {
      const envelope = await readErrorEnvelope(response)
      throw new ApiError(envelope.code, envelope.message, response.status)
    }

    try {
      return (await response.json()) as T
    } catch {
      // Corpo cortado pelo timeout é falta de resposta, não resposta estranha.
      throw controller.signal.aborted
        ? semResposta()
        : new ApiError('erro_interno', 'Resposta inesperada do servidor.', response.status)
    }
  } finally {
    clearTimeout(timer)
  }
}

/** Limites vigentes no servidor. O cliente valida contra eles, sem repeti-los. */
export function fetchConfig(): Promise<AppConfig> {
  return request<AppConfig>('/config')
}

/** Estado corrente de um documento, para acompanhar o processamento. */
export function fetchDocument(documentId: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${encodeURIComponent(documentId)}`)
}

/**
 * Envia o PDF.
 *
 * O campo do multipart é `file`, como a §4.5 fixa. O `Content-Type` fica a
 * cargo do navegador: defini-lo à mão apagaria o `boundary` e o servidor
 * recusaria o corpo.
 */
export function uploadDocument(file: File): Promise<UploadAccepted> {
  const body = new FormData()
  body.append('file', file)
  return request<UploadAccepted>('/documents', { method: 'POST', body }, UPLOAD_TIMEOUT_MS)
}
