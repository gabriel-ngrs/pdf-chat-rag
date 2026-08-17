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
 * Junta o histórico do servidor ao que já está na tela, sem perder nenhum lado.
 *
 * O que está na tela pode ser uma pergunta feita antes de o histórico chegar —
 * ela tem id local (negativo) e nunca colide com os ids do servidor. Descartar
 * um dos lados custaria caro nos dois sentidos: sobrescrever apagaria a
 * pergunta em voo, e ignorar o servidor faria a conversa anterior sumir da tela
 * pelo resto da sessão.
 */
function mergeHistory(history: ChatMessage[], current: ChatMessage[]): ChatMessage[] {
  const restored = new Set(history.map((message) => message.id))
  return [...history, ...current.filter((message) => !restored.has(message.id))]
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
  // servidor, pela conversa que já existia. Entra mesclado, não sobrescrevendo:
  // uma pergunta feita antes de o histórico chegar continua na tela, e a
  // conversa anterior aparece acima dela.
  useEffect(() => {
    if (!conversationId) {
      return
    }
    let active = true
    void listMessages(conversationId)
      .then((history) => {
        if (active && history.length > 0) {
          setMessages((current) => mergeHistory(history, current))
        }
      })
      .catch(() => {
        // Histórico indisponível não impede perguntar de novo.
      })
    return () => {
      active = false
    }
  }, [conversationId])

  // Sair da tela — ou trocar de conversa — no meio da resposta encerra o
  // stream: sem isto o gerador continuaria consumindo quota de um usuário que
  // já não está olhando, e os tokens da conversa anterior chegariam na nova.
  useEffect(() => {
    return () => {
      controllerRef.current?.abort()
      controllerRef.current = null
    }
  }, [conversationId])

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

      // O id fica guardado porque a pergunta pode precisar sair da lista: uma
      // falha antes do primeiro token devolve a pergunta ao campo, e deixar o
      // balão para trás faria "Tentar de novo" empilhar a mesma pergunta duas
      // vezes na conversa, sem resposta entre elas.
      const optimisticId = nextLocalId.current--
      setMessages((previous) => [
        ...previous,
        {
          id: optimisticId,
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
        let failed = false

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
              failed = true
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
            failed = true
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
          } else if (failed) {
            // Falhou sem nenhum token: a pergunta volta para o campo, e a
            // conversa não guarda um balão órfão. Cancelamento não entra aqui —
            // desistir é decisão de quem perguntou, e a pergunta continua tendo
            // acontecido.
            setMessages((previous) => previous.filter((message) => message.id !== optimisticId))
          }
        }
      }

      void run()
    },
    [conversationId],
  )

  return { messages, streaming, failure, send, cancel }
}
