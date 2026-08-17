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
