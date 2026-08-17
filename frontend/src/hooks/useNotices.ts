import { toast } from 'sonner'

import { describeError } from '@/lib/errors'
import type { NoticeSeverity } from '@/lib/errors'

/** Erro fica mais tempo na tela: tem uma ação para ler e decidir. */
const ERROR_DURATION_MS = 8_000
const NEUTRAL_DURATION_MS = 4_000

type ErrorOverrides = {
  /**
   * Substitui a frase do mapa quando a interface sabe algo mais específico —
   * por exemplo o tamanho real do arquivo recusado antes do envio.
   */
  message?: string
}

/**
 * Camada única de avisos do TalkDoc.
 *
 * Erro entra **por código**, nunca por texto solto: é o que garante que a mesma
 * falha diga a mesma coisa em qualquer tela, e que a FEAT-0002 reaproveite as
 * frases sem reescrevê-las.
 */
export const notify = {
  info(message: string) {
    toast.info(message, { duration: NEUTRAL_DURATION_MS })
  },

  success(message: string) {
    toast.success(message, { duration: NEUTRAL_DURATION_MS })
  },

  error(code: string, overrides: ErrorOverrides = {}) {
    const { title, message, action } = describeError(code)
    toast.error(title, {
      description: `${overrides.message ?? message} ${action}`,
      duration: ERROR_DURATION_MS,
    })
  },
}

export type Notices = typeof notify
export type { NoticeSeverity }

/** Acesso aos avisos de dentro de um componente. */
export function useNotices(): Notices {
  return notify
}
