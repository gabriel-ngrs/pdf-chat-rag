/**
 * Tipos do contrato de API, escritos a partir da §4.5 da spec — não gerados do
 * backend. O contrato é a fonte única; se os dois lados divergirem, quem está
 * errado é o código, não este arquivo.
 *
 * Os nomes de campo são os do JSON (snake_case) de propósito: renomear aqui
 * criaria uma camada de tradução que esconderia a divergência em vez de expô-la.
 */

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

/** Resposta de `POST /api/documents` (202). */
export type UploadAccepted = {
  id: string
  status: DocumentStatus
}

/** Resposta de `GET /api/documents/{id}`. */
export type DocumentDetail = {
  id: string
  filename: string
  status: DocumentStatus
  page_count: number | null
  chunks_total: number | null
  chunks_processed: number
  error_message: string | null
}

/**
 * Resposta de `GET /api/config` — os limites que o servidor aplica de fato.
 * O cliente valida contra estes números em vez de repeti-los em constante.
 */
export type AppConfig = {
  max_upload_mb: number
  max_pdf_pages: number
  max_extracted_chars: number
}

/** Envelope de erro da §4.3, único para toda resposta 4xx/5xx. */
export type ErrorEnvelope = {
  code: string
  message: string
}

/**
 * Trecho do documento que sustentou uma resposta, como vem no evento
 * `citations` da FEAT-0002 §4.3.
 *
 * O `snippet` já chega recortado em 240 caracteres pelo servidor — o cliente
 * exibe, não recorta de novo.
 */
export type Citation = {
  page_number: number
  snippet: string
  chunk_index: number
  score: number
}

export type ChatRole = 'user' | 'assistant'

/** Item de `GET /api/conversations/{id}/messages` (FEAT-0002 §4.4). */
export type ChatMessage = {
  id: number
  role: ChatRole
  content: string
  citations: Citation[]
  /** A resposta foi persistida incompleta — o stream caiu antes do fim. */
  truncated: boolean
  created_at: string
}

/** Resposta de `POST /api/conversations` (201). */
export type ConversationCreated = {
  id: string
}
