import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, listMessages, openChatStream } from '@/lib/api'
import { parseChatStream } from '@/lib/sse'
import type { ChatMessage, Citation } from '@/lib/types'

/** A resposta enquanto ela chega. Vira `ChatMessage` quando o stream fecha. */
export type StreamingAnswer = {
  content: string
  citations: Citation[]
}

/**
 * A última falha do turno, com a pergunta que a provocou.
 *
 * O hook **reporta** a falha em vez de avisar direto: quem sabe oferecer o
 * caminho de volta — repor a pergunta no campo, repetir o envio — é a tela.
 */
export type ChatFailure = {
  code: string
  question: string
}

export type ChatSession = {
  messages: ChatMessage[]
  /** Não-nulo do envio até o fim do stream; conteúdo vazio = ainda pensando. */
  streaming: StreamingAnswer | null
  failure: ChatFailure | null
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
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState<StreamingAnswer | null>(null)
  const [failure, setFailure] = useState<ChatFailure | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const nextLocalId = useRef(-1)

  // Recarregar a página não pode custar a conversa: o histórico volta do
  // servidor, pela conversa que já existia. Só entra se a lista ainda estiver
  // vazia — uma pergunta feita antes da resposta chegar não pode ser apagada
  // por ela.
  useEffect(() => {
    if (!conversationId) {
      return
    }
    let active = true
    void listMessages(conversationId)
      .then((history) => {
        if (active && history.length > 0) {
          setMessages((current) => (current.length === 0 ? history : current))
        }
      })
      .catch(() => {
        // Histórico indisponível não impede perguntar de novo.
      })
    return () => {
      active = false
    }
  }, [conversationId])

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
      setFailure(null)

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
              setFailure({ code: event.code, question: asked })
              break
            } else {
              messageId = event.messageId
              truncated = event.truncated
              break
            }
          }
        } catch (error) {
          if (controller.signal.aborted) {
            // Cancelar é uma decisão de quem pergunta, não uma falha.
            truncated = content.length > 0
          } else {
            setFailure({
              code: error instanceof ApiError ? error.code : 'erro_interno',
              question: asked,
            })
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
    [conversationId],
  )

  return { messages, streaming, failure, send, cancel }
}
