import { useCallback, useState } from 'react'

import { useNotices } from '@/hooks/useNotices'
import { ApiError, uploadDocument } from '@/lib/api'
import { maxUploadBytes } from '@/lib/config'
import type { AppConfig, UploadAccepted } from '@/lib/types'

export type UploadState =
  | { status: 'idle' }
  | { status: 'sending' }
  | { status: 'error'; code: string }

export type SelectionProblem = {
  code: string
  /** Mensagem específica desta recusa; título e ação continuam vindo do mapa. */
  message: string
}

/** Formata bytes para o usuário. MB com uma casa é o que dá para comparar com o limite. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`
}

/**
 * Confere o arquivo escolhido contra os limites que o servidor informou.
 *
 * Isto **não substitui** a validação do servidor: existe para responder na hora,
 * antes de gastar uma requisição e a paciência de quem está esperando. Sem
 * limites conhecidos (config degradada) a checagem de tamanho não acontece — e
 * quem recusa passa a ser o servidor, que é quem sempre teve a palavra final.
 */
export function validateSelection(file: File, limits: AppConfig | null): SelectionProblem | null {
  const looksLikePdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
  if (!looksLikePdf) {
    return {
      code: 'arquivo_invalido',
      message: 'Só é possível enviar arquivos PDF.',
    }
  }

  if (limits && file.size > maxUploadBytes(limits)) {
    return {
      code: 'arquivo_grande',
      message: `O arquivo tem ${formatFileSize(file.size)} e o limite é ${limits.max_upload_mb} MB.`,
    }
  }

  return null
}

/**
 * Envio do PDF.
 *
 * Não existe progresso de envio aqui: `fetch` não reporta bytes enviados, e
 * inventar uma barra que não mede nada seria mentir. O indicador é
 * indeterminado; a barra que importa é a do processamento, na tela seguinte.
 */
export function useUpload() {
  const notify = useNotices()
  const [state, setState] = useState<UploadState>({ status: 'idle' })

  const send = useCallback(
    async (file: File): Promise<UploadAccepted | null> => {
      setState({ status: 'sending' })
      try {
        const accepted = await uploadDocument(file)
        setState({ status: 'idle' })
        return accepted
      } catch (error) {
        const code = error instanceof ApiError ? error.code : 'erro_interno'
        setState({ status: 'error', code })
        notify.error(code)
        return null
      }
    },
    [notify],
  )

  return { state, send }
}
