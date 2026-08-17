import { toast } from 'sonner'

import { describeError } from '@/lib/errors'
import type { NoticeSeverity } from '@/lib/errors'

/** Erro fica mais tempo na tela: tem uma ação para ler e decidir. */
const ERROR_DURATION_MS = 8_000
const NEUTRAL_DURATION_MS = 4_000

/**
 * A severidade do mapa é quem escolhe o canal e a duração.
 *
 * Sem esta tabela o `severity` de `ErrorDescription` seria decoração: um código
 * futuro marcado como aviso sairia como erro vermelho, porque o despacho estaria
 * fixo em `toast.error`.
 */
const CHANNEL_BY_SEVERITY: Record<NoticeSeverity, { show: typeof toast.error; duration: number }> = {
  info: { show: toast.info, duration: NEUTRAL_DURATION_MS },
  success: { show: toast.success, duration: NEUTRAL_DURATION_MS },
  error: { show: toast.error, duration: ERROR_DURATION_MS },
}

type ErrorOverrides = {
  /**
   * Substitui a frase do mapa quando a interface sabe algo mais específico —
   * por exemplo o tamanho real do arquivo recusado antes do envio.
   */
  message?: string
  /**
   * Ação de recuperação dentro do próprio aviso.
   *
   * O mapa diz o que fazer ("tente de novo"); quando a tela sabe **como** fazer,
   * o aviso passa a ter o botão em vez de deixar a instrução por conta de quem
   * lê.
   */
  action?: { label: string; onClick: () => void }
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
    const { title, message, action, severity } = describeError(code)
    const { show, duration } = CHANNEL_BY_SEVERITY[severity]
    show(title, {
      description: `${overrides.message ?? message} ${action}`,
      duration,
      action: overrides.action,
    })
  },
}

export type Notices = typeof notify
export type { NoticeSeverity }

/**
 * Acesso aos avisos de dentro de um componente.
 *
 * Hoje devolve a constante de módulo e nada mais — é indireção deliberada, para
 * que trocar o `sonner` por um provider com estado (fila, agrupamento) seja uma
 * mudança neste arquivo, e não em todo componente que avisa alguma coisa.
 * Por ser estável, é seguro em lista de dependência de efeito.
 */
export function useNotices(): Notices {
  return notify
}
