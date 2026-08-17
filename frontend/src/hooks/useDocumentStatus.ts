import { useEffect, useRef, useState } from 'react'

import { ApiError, fetchDocument } from '@/lib/api'
import type { DocumentDetail } from '@/lib/types'

/**
 * Intervalo entre leituras.
 *
 * O backend atualiza o progresso a cada lote de embeddings (no máximo a cada
 * 15 s), então perguntar mais rápido que isto não revela nada de novo — 1,5 s é
 * o suficiente para a tela parecer viva sem virar enxurrada de requisição.
 */
const POLL_INTERVAL_MS = 1_500

/**
 * Percentual da leitura, ou `null` quando ainda não existe percentual honesto.
 *
 * `chunks_total` só é conhecido depois do chunking; nessa janela o progresso é
 * legitimamente indeterminado, e inventar um número seria mentir sobre o que o
 * backend informou.
 */
export function progressPercent(document: DocumentDetail | null): number | null {
  if (!document || !document.chunks_total) {
    return null
  }
  const percent = Math.round((document.chunks_processed / document.chunks_total) * 100)
  return Math.min(100, Math.max(0, percent))
}

export type DocumentStatusState = {
  /** Último estado conhecido. Sobrevive a uma falha de rede de propósito. */
  document: DocumentDetail | null
  /** O documento salvo não existe mais no servidor (404). */
  missing: boolean
  /** Ainda não houve nenhuma leitura bem-sucedida. */
  loading: boolean
}

const IDLE: DocumentStatusState = { document: null, missing: false, loading: false }

/**
 * Acompanha um documento até ele terminar.
 *
 * Para de perguntar em `ready` e em `failed` — estado terminal não muda mais, e
 * continuar consultando só gasta bateria e log. Falha de rede **não** derruba o
 * que já se sabe: a tela continua mostrando o último estado e a próxima
 * tentativa acontece no ciclo seguinte.
 */
export function useDocumentStatus(documentId: string | null): DocumentStatusState {
  const [state, setState] = useState<DocumentStatusState>(IDLE)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!documentId) {
      setState(IDLE)
      return
    }

    let cancelled = false
    setState({ document: null, missing: false, loading: true })

    async function poll() {
      if (cancelled || !documentId) {
        return
      }
      try {
        const document = await fetchDocument(documentId)
        if (cancelled) {
          return
        }
        setState({ document, missing: false, loading: false })
        if (document.status === 'ready' || document.status === 'failed') {
          return
        }
      } catch (error) {
        if (cancelled) {
          return
        }
        if (error instanceof ApiError && error.code === 'nao_encontrado') {
          setState({ document: null, missing: true, loading: false })
          return
        }
        // Qualquer outra falha é transitória até prova em contrário: mantém o
        // último estado conhecido e tenta de novo no próximo ciclo.
        setState((previous) => ({ ...previous, loading: false }))
      }
      timerRef.current = setTimeout(() => void poll(), POLL_INTERVAL_MS)
    }

    void poll()

    return () => {
      cancelled = true
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [documentId])

  return state
}
