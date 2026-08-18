import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { SearchXIcon, TriangleAlertIcon } from 'lucide-react'

import { CitationChip } from '@/components/CitationChip'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import type { StreamingAnswer } from '@/hooks/useChat'
import type { ChatMessage, Citation } from '@/lib/types'
import { cn } from '@/lib/utils'

/**
 * Folga, em pixels, para considerar que a pessoa está no fim da conversa.
 *
 * Sem essa folga, um scroll de um pixel para cima já desligaria o
 * acompanhamento automático — e a resposta seguinte pareceria não chegar.
 */
const NEAR_BOTTOM_PX = 48

/**
 * A pessoa está no fim da conversa (ou perto o bastante)?
 *
 * Função pura porque é a única decisão do acompanhamento de scroll que dá para
 * provar sem layout: o jsdom não calcula altura nenhuma, e testar a regra pela
 * tela exigiria um navegador de verdade para conferir uma subtração.
 */
export function isNearBottom(scrollHeight: number, scrollTop: number, clientHeight: number): boolean {
  return scrollHeight - scrollTop - clientHeight <= NEAR_BOTTOM_PX
}

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
      following.current = isNearBottom(
        viewport.scrollHeight,
        viewport.scrollTop,
        viewport.clientHeight,
      )
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

/**
 * Os trechos consultados numa resposta, da página menor para a maior.
 *
 * "Consultados", e não "citados": são os que passaram do limiar de similaridade
 * e entraram no prompt, e o modelo não se apoia em todos eles (BUG-003).
 *
 * Resposta sem citação não rende área nenhuma — nem título, nem espaço vazio:
 * citação vazia é recusa por falta de fundamento, e a `B.4` cuida de mostrá-la
 * como resposta legítima. Um cabeçalho "Citações" sobre o nada diria que algo
 * falhou.
 */
function Citations({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return null
  }
  const ordered = [...citations].sort(
    (left, right) =>
      left.page_number - right.page_number || left.chunk_index - right.chunk_index,
  )

  return (
    <ul aria-label="Trechos consultados para esta resposta" className="flex flex-wrap gap-2 pt-1">
      {ordered.map((citation) => (
        <li key={`${citation.page_number}-${citation.chunk_index}`}>
          <CitationChip citation={citation} />
        </li>
      ))}
    </ul>
  )
}

/**
 * Recusa por falta de fundamento.
 *
 * O sinal vem do contrato: sem nenhum trecho acima do limiar, o servidor
 * responde a recusa padrão com `citations` vazio (FR-6). Resposta **interrompida**
 * fica de fora — ela pode estar sem citação só porque o stream caiu antes do
 * evento, e chamar isso de recusa seria inventar um significado.
 */
function isRefusal(message: ChatMessage): boolean {
  return message.role === 'assistant' && !message.truncated && message.citations.length === 0
}

type AssistantMessageProps = {
  content: string
  citations: Citation[]
  truncated?: boolean
  /** Recusa é resposta legítima: marcação sutil, nunca aparência de erro. */
  refused?: boolean
}

function AssistantMessage({
  content,
  citations,
  truncated = false,
  refused = false,
}: AssistantMessageProps) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground flex items-center gap-2 font-mono text-caption tracking-widest uppercase">
        <span aria-hidden="true">Resposta</span>
        <span className="sr-only">O TalkDoc respondeu:</span>
        {refused ? (
          <span className="flex items-center gap-1 tracking-normal normal-case">
            <SearchXIcon className="size-3.5" aria-hidden="true" />
            sem base no documento
          </span>
        ) : null}
      </p>
      <div className={cn('max-w-prose whitespace-pre-wrap', refused && 'text-muted-foreground')}>
        {content}
      </div>
      {truncated ? (
        <p className="text-warning flex items-center gap-1 text-caption">
          <TriangleAlertIcon className="size-3.5" aria-hidden="true" />
          Resposta interrompida antes do fim.
        </p>
      ) : null}
      <Citations citations={citations} />
    </div>
  )
}

/**
 * O "pensando", entre o envio e o primeiro token.
 *
 * O `role="status"` anuncia a espera uma vez, mesmo dentro do item que silencia
 * os tokens: quem não vê a tela precisa saber que o sistema está trabalhando.
 */
function ThinkingIndicator() {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground font-mono text-caption tracking-widest uppercase">
        Resposta
      </p>
      <span role="status" className="sr-only">
        Pensando na resposta.
      </span>
      <div className="flex flex-col gap-2" aria-hidden="true">
        <Skeleton className="h-4 w-full max-w-prose" />
        <Skeleton className="h-4 w-3/5" />
      </div>
    </div>
  )
}

type MessageListProps = {
  messages: ChatMessage[]
  /** Resposta em construção, ainda fora do histórico. */
  streaming?: StreamingAnswer | null
  /** O que mostrar antes da primeira pergunta. */
  emptyState?: ReactNode
}

/**
 * A conversa.
 *
 * A resposta do assistente é texto corrido, sem balão: o produto é sobre ler um
 * documento, e a resposta é a leitura — quem tem balão é a pergunta, que é o
 * comentário na margem.
 */
export function MessageList({ messages, streaming = null, emptyState = null }: MessageListProps) {
  // O que faz a lista crescer é uma mensagem nova ou mais um token: acompanhar
  // esses dois tamanhos evita reagir a render que não mudou nada na conversa.
  const containerRef = useStickToBottom(`${messages.length}:${streaming?.content.length ?? -1}`)

  return (
    <ScrollArea ref={containerRef} className="h-full">
      <ol
        aria-label="Conversa"
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
              <AssistantMessage
                content={message.content}
                citations={message.citations}
                truncated={message.truncated}
                refused={isRefusal(message)}
              />
            )}
          </li>
        ))}

        {streaming ? (
          // A resposta em construção fica muda para o leitor de tela: anunciar
          // token a token viraria ruído. O anúncio acontece uma vez, quando a
          // mensagem pronta entra na lista acima.
          <li aria-live="off" aria-busy="true">
            {streaming.content ? (
              <AssistantMessage content={streaming.content} citations={streaming.citations} />
            ) : (
              <ThinkingIndicator />
            )}
          </li>
        ) : null}
      </ol>

      {messages.length === 0 && !streaming ? emptyState : null}
    </ScrollArea>
  )
}
