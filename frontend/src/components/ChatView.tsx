import { useCallback, useEffect, useRef, useState } from 'react'
import { SquareIcon } from 'lucide-react'

import { MessageInput } from '@/components/MessageInput'
import { MessageList } from '@/components/MessageList'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useChat } from '@/hooks/useChat'
import { useNotices } from '@/hooks/useNotices'
import { ApiError, createConversation } from '@/lib/api'
import type { DocumentDetail } from '@/lib/types'

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
        <h1 className="font-display text-title text-balance">Converse com o documento</h1>
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
 * Tela de conversa.
 *
 * A altura é fixada em relação à viewport para o campo de pergunta ficar sempre
 * visível: numa conversa longa, um rodapé que desce com a página obrigaria a
 * rolar até o fim para perguntar de novo.
 */
export function ChatView({ document, onReset }: ChatViewProps) {
  const conversation = useConversation(document.id)
  const conversationId = conversation.status === 'open' ? conversation.conversationId : null
  const { messages, streaming, send, cancel } = useChat(conversationId)
  const [question, setQuestion] = useState('')

  const handleSubmit = useCallback(() => {
    send(question)
    setQuestion('')
  }, [question, send])

  return (
    // 14rem é o que a casca ocupa fora do conteúdo (cabeçalho, respiro vertical
    // do `main` e rodapé). É valor calculado, não escolhido: sem ele a lista
    // cresceria para além da tela e o campo de pergunta iria junto.
    <div className="flex h-[calc(100dvh-14rem)] min-h-96 flex-col gap-4">
      <DocumentHeader document={document} onReset={onReset} />

      <div className="min-h-0 flex-1">
        {conversation.status === 'opening' ? (
          <div className="flex flex-col gap-4 py-6" aria-busy="true">
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-4 w-72" />
          </div>
        ) : (
          <MessageList messages={messages} streaming={streaming} />
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
