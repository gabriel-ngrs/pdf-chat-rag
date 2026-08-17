import { getSessionId } from '@/lib/session'
import type {
  AppConfig,
  ChatMessage,
  ConversationCreated,
  DocumentDetail,
  ErrorEnvelope,
  UploadAccepted,
} from '@/lib/types'

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

/**
 * Abre uma conversa sobre um documento.
 *
 * O servidor recusa documento que não esteja `ready` com `documento_nao_pronto`
 * — quem decide se dá para conversar é ele, não a tela.
 */
export function createConversation(documentId: string): Promise<ConversationCreated> {
  return request<ConversationCreated>('/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_id: documentId }),
  })
}

/** Histórico da conversa, com as citações presas às respostas. */
export function listMessages(conversationId: string): Promise<ChatMessage[]> {
  return request<ChatMessage[]>(`/conversations/${encodeURIComponent(conversationId)}/messages`)
}

/**
 * Abre o fluxo de resposta de uma pergunta e devolve a resposta já conferida.
 *
 * Não passa pelo `request()`: aquele lê o corpo inteiro como JSON, que é
 * exatamente o que não se pode fazer com um stream. Duas conferências acontecem
 * aqui, **antes** de qualquer parser de SSE ver o corpo (FR-11): status de erro
 * — o `429` do provedor chega quase sempre antes do primeiro byte, como JSON — e
 * `Content-Type`, porque um proxy mal configurado devolve HTML com `200`.
 *
 * Sem timeout de propósito: uma resposta longa demora, e quem corta é o
 * `AbortSignal` de quem cancelou ou saiu da tela.
 */
export async function openChatStream(
  conversationId: string,
  question: string,
  signal: AbortSignal,
): Promise<Response> {
  const path = `/conversations/${encodeURIComponent(conversationId)}/messages`

  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      signal,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'X-Session-Id': getSessionId(),
      },
      body: JSON.stringify({ question }),
    })
  } catch (error) {
    // Cancelamento não é falha de rede: quem abortou sabe o que fez.
    if (signal.aborted) {
      throw error
    }
    throw new ApiError('rede_indisponivel', 'Não foi possível falar com o servidor.', null)
  }

  if (!response.ok) {
    const envelope = await readErrorEnvelope(response)
    throw new ApiError(envelope.code, envelope.message, response.status)
  }

  if (!(response.headers.get('Content-Type') ?? '').includes('text/event-stream')) {
    throw new ApiError('erro_interno', 'O servidor não abriu o fluxo de resposta.', response.status)
  }

  return response
}
