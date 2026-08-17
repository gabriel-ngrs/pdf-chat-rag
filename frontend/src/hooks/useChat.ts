import { useCallback, useEffect, useRef, useState } from 'react'

import { useNotices } from '@/hooks/useNotices'
import { ApiError, openChatStream } from '@/lib/api'
import { parseChatStream } from '@/lib/sse'
import type { ChatMessage, Citation } from '@/lib/types'

/** A resposta enquanto ela chega. Vira `ChatMessage` quando o stream fecha. */
export type StreamingAnswer = {
  content: string
  citations: Citation[]
}

export type ChatSession = {
  messages: ChatMessage[]
  /** Não-nulo do envio até o fim do stream; conteúdo vazio = ainda pensando. */
  streaming: StreamingAnswer | null
  send: (question: string) => void
  cancel: () => void
}

function nowIso(): string {
  return new Date().toISOString()
}

/**
 * Um turno de conversa, do envio ao último token.
 *
 * A resposta em construção fica **fora** da lista de mensagens: enquanto ela é
 * um rascunho que muda a cada token, misturá-la ao histórico obrigaria a
 * reescrever o último item o tempo todo e faria a região viva anunciar cada
 * token para quem usa leitor de tela.
 *
 * O conteúdo recebido é acumulado em variáveis locais, não lido do estado: o
 * estado do React é assíncrono, e fechar a mensagem a partir dele perderia os
 * últimos tokens.
 */
export function useChat(conversationId: string | null): ChatSession {
  const notify = useNotices()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState<StreamingAnswer | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const nextLocalId = useRef(-1)

  // Sair da tela no meio da resposta encerra o stream: sem isto o gerador
  // continuaria consumindo quota de um usuário que já não está olhando.
  useEffect(() => {
    return () => {
      controllerRef.current?.abort()
      controllerRef.current = null
    }
  }, [])

  const cancel = useCallback(() => {
    controllerRef.current?.abort()
  }, [])

  const send = useCallback(
    (question: string) => {
      const asked = question.trim()
      if (!conversationId || !asked || controllerRef.current) {
        return
      }

      const openConversationId = conversationId
      const controller = new AbortController()
      controllerRef.current = controller

      setMessages((previous) => [
        ...previous,
        {
          id: nextLocalId.current--,
          role: 'user',
          content: asked,
          citations: [],
          truncated: false,
          created_at: nowIso(),
        },
      ])
      setStreaming({ content: '', citations: [] })

      async function run() {
        let content = ''
        let citations: Citation[] = []
        let truncated = false
        let messageId: number | null = null

        try {
          const response = await openChatStream(openConversationId, asked, controller.signal)
          for await (const event of parseChatStream(response)) {
            if (event.type === 'token') {
              content += event.text
              setStreaming({ content, citations })
            } else if (event.type === 'citations') {
              citations = event.citations
              setStreaming({ content, citations })
            } else if (event.type === 'error') {
              // Falha depois do primeiro byte: o que chegou continua valendo,
              // mas a resposta não está completa e não pode parecer completa.
              truncated = true
              notify.error(event.code)
              break
            } else {
              messageId = event.messageId
              truncated = event.truncated
              break
            }
          }
        } catch (error) {
          if (controller.signal.aborted) {
            truncated = content.length > 0
          } else {
            notify.error(error instanceof ApiError ? error.code : 'erro_interno')
          }
        } finally {
          controllerRef.current = null
          setStreaming(null)
          if (content) {
            setMessages((previous) => [
              ...previous,
              {
                id: messageId ?? nextLocalId.current--,
                role: 'assistant',
                content,
                citations,
                truncated,
                created_at: nowIso(),
              },
            ])
          }
        }
      }

      void run()
    },
    [conversationId, notify],
  )

  return { messages, streaming, send, cancel }
}
