import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { SearchXIcon, TriangleAlertIcon } from 'lucide-react'

import { CitationChip } from '@/components/CitationChip'
import { Markdown } from '@/components/Markdown'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { StreamingAnswer } from '@/hooks/useChat'
import { useReducedMotion } from '@/hooks/useReducedMotion'
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
 * Defasagem entre a entrada de um chip de citação e a do seguinte, em ms.
 *
 * Vinte é o suficiente para o olho ler "estes vieram juntos" e curto demais
 * para virar espera: cinco chips fecham a entrada em 80 ms de defasagem mais os
 * 220 ms da animação. Acima disso o último chip pareceria ter chegado depois.
 */
const CHIP_STAGGER_MS = 20

/**
 * A malha de nove peças do indicador "pensando".
 *
 * A defasagem é diagonal — `(linha + coluna)` — e não sequencial: uma onda que
 * atravessa a malha lê como coisa se juntando, enquanto acender da esquerda
 * para a direita lê como barra de progresso, que é uma promessa que não se pode
 * cumprir aqui (não há percentual de raciocínio para reportar).
 */
const THINKING_TILES = Array.from({ length: 9 }, (_, index) => ({
  index,
  delay: (Math.floor(index / 3) + (index % 3)) * 110,
}))

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

/**
 * A pergunta, como balão na margem.
 *
 * O rótulo de leitor de tela vive FORA do balão e com `select-none`, e as duas
 * coisas são necessárias: fora do balão, selecionar só o texto não o pega; com
 * `select-none`, arrastar a seleção por cima da mensagem inteira também não.
 * Antes da MELH-001 ele era filho do balão, e quem copiava uma pergunta colava
 * "Você perguntou:" grudado nela.
 */
function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <span className="sr-only select-none">Você perguntou:</span>
      <div className="bg-secondary text-secondary-foreground max-w-[85%] rounded-lg px-4 py-3 whitespace-pre-wrap">
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
function Citations({ citations, reducedMotion }: { citations: Citation[]; reducedMotion: boolean }) {
  if (citations.length === 0) {
    return null
  }
  const ordered = [...citations].sort(
    (left, right) =>
      left.page_number - right.page_number || left.chunk_index - right.chunk_index,
  )

  return (
    <ul aria-label="Trechos consultados para esta resposta" className="flex flex-wrap gap-2 pt-1">
      {ordered.map((citation, index) => (
        <li
          key={`${citation.page_number}-${citation.chunk_index}`}
          // A entrada escalonada é o movimento que explica uma relação real:
          // estes chips chegaram junto com aquela resposta. Sob movimento
          // reduzido não há classe nem atraso — a regra do `index.css` alcança
          // a duração, mas quem decide se a animação existe é este `if`.
          className={reducedMotion ? undefined : 'animate-rise'}
          style={reducedMotion ? undefined : { animationDelay: `${index * CHIP_STAGGER_MS}ms` }}
        >
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
  /**
   * A resposta ainda está chegando token a token.
   *
   * Enquanto está, o texto é impresso cru; o Markdown só entra quando a
   * resposta fecha. O motivo é que Markdown em construção é Markdown
   * **inválido** na maior parte do tempo — `**Estratég` antes do negrito
   * fechar —, e reprocessar a string inteira a cada token faria o parágrafo
   * refluir a cada frame. A lista mede `scrollHeight` para se manter no fim, e
   * uma altura que oscila é uma lista que perde o fim.
   */
  streaming?: boolean
  /** Vem de fora porque a lista já perguntou uma vez, para todas as mensagens. */
  reducedMotion?: boolean
}

function AssistantMessage({
  content,
  citations,
  truncated = false,
  refused = false,
  streaming = false,
  reducedMotion = false,
}: AssistantMessageProps) {
  return (
    <div className="flex flex-col gap-2">
      {/* `select-none` na linha inteira: "Resposta" é etiqueta de interface, e
          o rótulo ao lado é para quem ouve. Nenhum dos dois é a resposta, e
          nenhum dos dois deve entrar no `Ctrl+C` de quem copia uma. */}
      <p className="text-muted-foreground flex items-center gap-2 font-mono text-caption tracking-widest uppercase select-none">
        <span aria-hidden="true">Resposta</span>
        <span className="sr-only">O TalkDoc respondeu:</span>
        {refused ? (
          <span className="flex items-center gap-1 tracking-normal normal-case">
            <SearchXIcon className="size-3.5" aria-hidden="true" />
            sem base no documento
          </span>
        ) : null}
      </p>
      {streaming ? (
        <div className="max-w-prose whitespace-pre-wrap">{content}</div>
      ) : (
        <Markdown className={cn('max-w-prose', refused && 'text-muted-foreground')}>
          {content}
        </Markdown>
      )}
      {truncated ? (
        <p className="text-warning flex items-center gap-1 text-caption">
          <TriangleAlertIcon className="size-3.5" aria-hidden="true" />
          Resposta interrompida antes do fim.
        </p>
      ) : null}
      <Citations citations={citations} reducedMotion={reducedMotion} />
    </div>
  )
}

/**
 * O "pensando", entre o envio e o primeiro token.
 *
 * Eram duas barras de esqueleto. Esqueleto promete forma: ele diz "o texto vem
 * com este tamanho", e aqui não se sabe o tamanho de nada — o que está
 * acontecendo é uma busca por trechos, não a chegada de um parágrafo. A malha
 * de peças diz a coisa certa: alguma coisa está sendo montada, e não há
 * percentual a mostrar.
 *
 * O `role="status"` anuncia a espera uma vez, mesmo dentro do item que silencia
 * os tokens: quem não vê a tela precisa saber que o sistema está trabalhando. A
 * malha é `aria-hidden` — ela não acrescenta informação a esse anúncio.
 */
function ThinkingIndicator({ reducedMotion = false }: { reducedMotion?: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground font-mono text-caption tracking-widest uppercase select-none">
        Resposta
      </p>
      <span role="status" className="sr-only">
        Pensando na resposta.
      </span>
      <div
        aria-hidden="true"
        className="border-border bg-muted/40 flex w-fit items-center gap-3 rounded-lg border px-3 py-2"
      >
        <span className="grid grid-cols-3 gap-[3px]">
          {THINKING_TILES.map((tile) => (
            <span
              key={tile.index}
              className={cn(
                'bg-primary size-[5px] rounded-[1px]',
                !reducedMotion && 'animate-think',
              )}
              style={reducedMotion ? undefined : { animationDelay: `${tile.delay}ms` }}
            />
          ))}
        </span>
        <span className="text-muted-foreground text-caption">Juntando os trechos…</span>
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
  // Uma consulta à media query para a conversa inteira: cada mensagem abrindo a
  // sua registraria um listener por item numa lista que só cresce.
  const reducedMotion = useReducedMotion()

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
          <li
            key={`${message.role}-${message.id}`}
            className={reducedMotion ? undefined : 'animate-rise'}
          >
            {message.role === 'user' ? (
              <UserMessage content={message.content} />
            ) : (
              <AssistantMessage
                content={message.content}
                citations={message.citations}
                truncated={message.truncated}
                refused={isRefusal(message)}
                reducedMotion={reducedMotion}
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
              <AssistantMessage
                content={streaming.content}
                citations={streaming.citations}
                streaming
                reducedMotion={reducedMotion}
              />
            ) : (
              <ThinkingIndicator reducedMotion={reducedMotion} />
            )}
          </li>
        ) : null}
      </ol>

      {messages.length === 0 && !streaming ? emptyState : null}
    </ScrollArea>
  )
}
