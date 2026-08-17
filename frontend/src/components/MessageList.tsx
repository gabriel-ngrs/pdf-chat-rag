import { useEffect, useRef } from 'react'

import { ScrollArea } from '@/components/ui/scroll-area'
import type { ChatMessage } from '@/lib/types'

/**
 * Folga, em pixels, para considerar que a pessoa está no fim da conversa.
 *
 * Sem essa folga, um scroll de um pixel para cima já desligaria o
 * acompanhamento automático — e a resposta seguinte pareceria não chegar.
 */
const NEAR_BOTTOM_PX = 48

function findViewport(container: HTMLElement | null): HTMLElement | null {
  // O elemento que rola é o viewport interno do Radix, e o wrapper do projeto
  // não expõe ref para ele. Buscar pelo `data-slot` é o acesso estável — é o
  // atributo que o próprio componente do design system escreve.
  return container?.querySelector<HTMLElement>('[data-slot="scroll-area-viewport"]') ?? null
}

/**
 * Mantém a conversa no fim, sem sequestrar o scroll.
 *
 * Se a pessoa subiu para reler uma resposta anterior, mensagem nova não pode
 * puxá-la de volta para baixo: o acompanhamento só continua ligado enquanto ela
 * está no fim da lista.
 */
function useStickToBottom(watched: unknown) {
  const containerRef = useRef<HTMLDivElement>(null)
  const following = useRef(true)

  useEffect(() => {
    const viewport = findViewport(containerRef.current)
    if (!viewport) {
      return
    }
    const handleScroll = () => {
      const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight
      following.current = distanceFromBottom <= NEAR_BOTTOM_PX
    }
    viewport.addEventListener('scroll', handleScroll, { passive: true })
    return () => viewport.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    if (!following.current) {
      return
    }
    const viewport = findViewport(containerRef.current)
    if (viewport) {
      viewport.scrollTop = viewport.scrollHeight
    }
  }, [watched])

  return containerRef
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="bg-secondary text-secondary-foreground max-w-[85%] rounded-lg px-4 py-3 whitespace-pre-wrap">
        <span className="sr-only">Você perguntou: </span>
        {content}
      </div>
    </div>
  )
}

function AssistantMessage({ content }: { content: string }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground font-mono text-caption tracking-widest uppercase">
        <span aria-hidden="true">Resposta</span>
        <span className="sr-only">O TalkDoc respondeu:</span>
      </p>
      <div className="max-w-prose whitespace-pre-wrap">{content}</div>
    </div>
  )
}

type MessageListProps = {
  messages: ChatMessage[]
}

/**
 * A conversa.
 *
 * A resposta do assistente é texto corrido, sem balão: o produto é sobre ler um
 * documento, e a resposta é a leitura — quem tem balão é a pergunta, que é o
 * comentário na margem.
 */
export function MessageList({ messages }: MessageListProps) {
  const containerRef = useStickToBottom(messages)

  return (
    <ScrollArea ref={containerRef} className="h-full">
      <ol
        className="flex flex-col gap-8 py-6 pr-4"
        // Região viva desde o primeiro render: `aria-live` inserido junto com o
        // conteúdo costuma não ser anunciado pelos leitores de tela.
        aria-live="polite"
        aria-atomic="false"
      >
        {messages.map((message) => (
          <li key={`${message.role}-${message.id}`}>
            {message.role === 'user' ? (
              <UserMessage content={message.content} />
            ) : (
              <AssistantMessage content={message.content} />
            )}
          </li>
        ))}
      </ol>
    </ScrollArea>
  )
}
