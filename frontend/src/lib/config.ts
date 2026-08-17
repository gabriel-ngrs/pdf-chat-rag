import { ApiError, fetchConfig } from '@/lib/api'
import type { AppConfig } from '@/lib/types'

/**
 * Estado dos limites do servidor.
 *
 * `degraded` é um estado de primeira classe, não um erro fatal: se
 * `GET /api/config` falhar, a aplicação continua utilizável e a validação local
 * simplesmente não acontece — quem recusa o arquivo passa a ser o servidor, que
 * é quem sempre teve a palavra final.
 */
export type ConfigState =
  | { status: 'loading' }
  | { status: 'ready'; limits: AppConfig }
  | { status: 'degraded'; code: string }

/**
 * Carrega os limites, traduzindo qualquer falha em estado degradado.
 *
 * Não existe limite de fallback em constante de propósito: um número repetido
 * aqui envelheceria em silêncio e passaria a mentir para o usuário.
 */
export async function loadConfig(): Promise<ConfigState> {
  try {
    return { status: 'ready', limits: await fetchConfig() }
  } catch (error) {
    return { status: 'degraded', code: error instanceof ApiError ? error.code : 'erro_interno' }
  }
}

/** Bytes correspondentes ao limite de upload, para comparar com `File.size`. */
export function maxUploadBytes(limits: AppConfig): number {
  return limits.max_upload_mb * 1024 * 1024
}
