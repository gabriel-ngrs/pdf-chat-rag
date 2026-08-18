import { useCallback, useEffect, useRef, useState } from 'react'
import { SquareIcon } from 'lucide-react'

import { MessageInput } from '@/components/MessageInput'
import { MessageList } from '@/components/MessageList'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useChat } from '@/hooks/useChat'
import { useNotices } from '@/hooks/useNotices'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { ApiError, createConversation } from '@/lib/api'
import type { DocumentDetail } from '@/lib/types'
import { cn } from '@/lib/utils'

/**
 * Uma conversa por documento.
 *
 * A chave guarda o par documento↔conversa: sem o documento junto, um `F5`
 * depois de trocar de PDF restauraria a conversa do documento anterior e as
 * citações apontariam para o arquivo errado.
 */
const CONVERSATION_STORAGE_KEY = 'talkdoc:conversation'

type StoredConversation = {
  documentId: string
  conversationId: string
}

function readStoredConversation(documentId: string): string | null {
  try {
    const raw = localStorage.getItem(CONVERSATION_STORAGE_KEY)
    if (!raw) {
      return null
    }
    const stored = JSON.parse(raw) as Partial<StoredConversation>
    return stored.documentId === documentId && typeof stored.conversationId === 'string'
      ? stored.conversationId
      : null
  } catch {
    // Conteúdo corrompido no storage não pode impedir a conversa de começar.
    return null
  }
}

function storeConversation(documentId: string, conversationId: string) {
  const stored: StoredConversation = { documentId, conversationId }
  localStorage.setItem(CONVERSATION_STORAGE_KEY, JSON.stringify(stored))
}

/** Esquece a conversa do documento corrente — usado ao trocar de documento. */
export function forgetConversation() {
  localStorage.removeItem(CONVERSATION_STORAGE_KEY)
}

type ConversationState =
  | { status: 'opening' }
  | { status: 'open'; conversationId: string }
  | { status: 'failed' }

/**
 * Abre (ou recupera) a conversa do documento.
 *
 * A guarda por `ref` é o ponto sensível desta fase: sem ela, cada render — e o
 * duplo efeito do modo estrito em desenvolvimento — criaria uma conversa nova
 * no servidor, e o histórico ficaria espalhado por várias.
 */
function useConversation(documentId: string): ConversationState {
  const notify = useNotices()
  const [state, setState] = useState<ConversationState>({ status: 'opening' })
  const requestedFor = useRef<string | null>(null)

  useEffect(() => {
    const restored = readStoredConversation(documentId)
    if (restored) {
      requestedFor.current = documentId
      setState({ status: 'open', conversationId: restored })
      return
    }
    if (requestedFor.current === documentId) {
      return
    }
    requestedFor.current = documentId

    // Sem bandeira de cancelamento no efeito de propósito: o modo estrito
    // desmonta e remonta o componente entre a chamada e a resposta, e uma
    // bandeira descartaria a única conversa criada. Atualizar o estado de um
    // componente já desmontado é inócuo — o estado morre com ele.
    void createConversation(documentId)
      .then((conversation) => {
        storeConversation(documentId, conversation.id)
        setState({ status: 'open', conversationId: conversation.id })
      })
      .catch((error: unknown) => {
        // Uma nova tentativa fica a cargo de quem recarrega a tela; repetir
        // sozinho aqui arriscaria criar duas conversas para o mesmo documento.
        requestedFor.current = null
        setState({ status: 'failed' })
        notify.error(error instanceof ApiError ? error.code : 'erro_interno')
      })
  }, [documentId, notify])

  return state
}

type ChatViewProps = {
  document: DocumentDetail
  /** Descarta o documento em acompanhamento e volta para o envio. */
  onReset: () => void
}

function DocumentHeader({ document, onReset }: ChatViewProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-title font-semibold text-balance">Converse com o documento</h1>
        <p className="text-muted-foreground tabular font-mono text-caption break-all">
          {document.filename}
          {document.page_count ? ` · ${document.page_count} páginas` : ''}
        </p>
      </div>
      <Button size="lg" variant="outline" onClick={onReset}>
        Enviar outro documento
      </Button>
    </div>
  )
}

/**
 * Perguntas de partida.
 *
 * São genéricas de propósito: o cliente não lê o conteúdo do PDF, e sugerir
 * "quais serviços a empresa oferece?" para um documento que não fala de empresa
 * nenhuma ensinaria a desconfiar da sugestão logo na primeira interação.
 */
const STARTER_QUESTIONS = [
  'Do que trata este documento?',
  'Quais são os pontos principais?',
  'Há alguma data ou prazo citado?',
]

function ConversationStart({ onSelect }: { onSelect: (question: string) => void }) {
  const reducedMotion = useReducedMotion()

  return (
    <div className={cn('flex flex-col gap-3 pb-6', !reducedMotion && 'animate-rise')}>
      <p className="text-muted-foreground max-w-prose text-caption">
        Pergunte o que quiser sobre o documento. Toda resposta vem com a página de onde saiu, ou
        com um “não encontrei isso aqui”.
      </p>
      <ul className="flex flex-wrap gap-2">
        {STARTER_QUESTIONS.map((starter, index) => (
          <li
            key={starter}
            // A mesma defasagem dos chips de citação, pelo mesmo motivo: as três
            // sugestões chegaram juntas, e entrar em fila diz isso.
            className={reducedMotion ? undefined : 'animate-rise'}
            style={reducedMotion ? undefined : { animationDelay: `${index * 40}ms` }}
          >
            <Button variant="outline" size="sm" onClick={() => onSelect(starter)}>
              {starter}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * O que ocupa o lugar das sugestões quando a conversa não chegou a abrir.
 *
 * Chip clicável aqui seria pior que chip nenhum: sem conversa, o clique morre
 * calado e a tela ensina a desconfiar do botão. O aviso da falha já saiu pelo
 * canal de avisos; o que falta dizer é o caminho de volta.
 */
function ConversationUnavailable() {
  return (
    <p className="text-muted-foreground max-w-prose py-6 text-caption">
      Não foi possível abrir a conversa para este documento. Recarregue a página para tentar de
      novo.
    </p>
  )
}

/**
 * Tela de conversa.
 *
 * A altura é fixada em relação à viewport para o campo de pergunta ficar sempre
 * visível: numa conversa longa, um rodapé que desce com a página obrigaria a
 * rolar até o fim para perguntar de novo.
 */
export function ChatView({ document, onReset }: ChatViewProps) {
  const notify = useNotices()
  const conversation = useConversation(document.id)
  const conversationId = conversation.status === 'open' ? conversation.conversationId : null
  const { messages, streaming, failure, send, cancel } = useChat(conversationId)
  const [question, setQuestion] = useState('')

  const ask = useCallback(
    (text: string) => {
      send(text)
      setQuestion('')
    },
    [send],
  )

  const handleSubmit = useCallback(() => ask(question), [ask, question])

  // A pergunta que falhou volta para o campo — perder o que a pessoa escreveu é
  // o pior detalhe possível —, e o aviso leva o botão que refaz o envio.
  useEffect(() => {
    if (!failure) {
      return
    }
    setQuestion((current) => (current === '' ? failure.question : current))
    notify.error(failure.code, {
      action: { label: 'Tentar de novo', onClick: () => ask(failure.question) },
    })
  }, [failure, notify, ask])

  return (
    // `h-full` em vez do `calc(100dvh - 14rem)` que estava aqui. Aquele 14rem
    // era a soma medida do cabeçalho, do respiro do `main` e do rodapé — um
    // número correto no dia em que foi escrito e errado no dia seguinte, porque
    // mudar o respiro do `main` (que é do `AppShell`) descolava a conta sem
    // avisar ninguém. O `main` é a linha `1fr` do grid da casca, então pedir a
    // altura dele resolve a mesma coisa e continua certo quando a casca muda.
    <div className="flex h-full min-h-96 flex-col gap-4">
      <DocumentHeader document={document} onReset={onReset} />

      {/* A conversa mora numa superfície própria, e não solta sobre a malha do
          fundo. Sem ela, o texto da resposta ficava direto sobre a textura: o
          contraste continuava passando, mas a leitura perdia a borda — não dava
          para dizer onde a conversa começa e onde o fundo termina.

          `overflow-hidden` para o conteúdo que rola respeitar o raio, e o
          `ScrollArea` de dentro continua sendo quem rola. */}
      <div className="border-border bg-card min-h-0 flex-1 overflow-hidden rounded-xl border px-4 sm:px-5">
        {conversation.status === 'opening' ? (
          <div className="flex flex-col gap-4 py-6" aria-busy="true">
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-4 w-72" />
          </div>
        ) : (
          <MessageList
            messages={messages}
            streaming={streaming}
            emptyState={
              conversation.status === 'open' ? (
                <ConversationStart onSelect={ask} />
              ) : (
                <ConversationUnavailable />
              )
            }
          />
        )}
      </div>

      {streaming ? (
        <div className="flex justify-center">
          <Button variant="outline" size="sm" onClick={cancel}>
            <SquareIcon aria-hidden="true" />
            Parar resposta
          </Button>
        </div>
      ) : null}

      <MessageInput
        value={question}
        onChange={setQuestion}
        onSubmit={handleSubmit}
        pending={streaming !== null}
        disabled={conversation.status !== 'open'}
      />
    </div>
  )
}
