import { useEffect, useRef } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { ArrowUpIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** Altura máxima do campo antes de ele passar a rolar, em pixels. */
const MAX_HEIGHT_PX = 160

type MessageInputProps = {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  /** Uma resposta está sendo gerada: enviar outra pergunta agora atropelaria. */
  pending: boolean
  /** A conversa ainda não existe (ou falhou ao ser criada). */
  disabled: boolean
}

/**
 * Campo de pergunta.
 *
 * É um `textarea` e não um `input` porque pergunta sobre documento costuma ter
 * mais de uma linha; `Enter` envia e `Shift+Enter` quebra linha, que é o que
 * quem usa chat já espera. O valor é controlado pelo `ChatView` de propósito:
 * quando o envio falha, a pergunta digitada precisa continuar lá.
 */
export function MessageInput({ value, onChange, onSubmit, pending, disabled }: MessageInputProps) {
  const fieldRef = useRef<HTMLTextAreaElement>(null)
  const canSend = value.trim().length > 0 && !pending && !disabled

  // O campo cresce com o texto até um teto. Sem zerar a altura antes de medir,
  // `scrollHeight` só sabe crescer e o campo nunca voltaria a encolher.
  useEffect(() => {
    const field = fieldRef.current
    if (!field) {
      return
    }
    field.style.height = 'auto'
    field.style.height = `${Math.min(field.scrollHeight, MAX_HEIGHT_PX)}px`
  }, [value])

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (canSend) {
      onSubmit()
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (canSend) {
        onSubmit()
      }
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        'border-border bg-card focus-within:border-ring focus-within:ring-ring/50 flex items-end gap-2 rounded-lg border p-2 transition-colors focus-within:ring-3',
      )}
    >
      <label htmlFor="chat-question" className="sr-only">
        Sua pergunta sobre o documento
      </label>
      <textarea
        id="chat-question"
        ref={fieldRef}
        rows={1}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Pergunte alguma coisa sobre o documento"
        className="placeholder:text-muted-foreground min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-body outline-none disabled:opacity-50"
      />
      <Button type="submit" size="icon-lg" disabled={!canSend} aria-label="Enviar pergunta">
        <ArrowUpIcon aria-hidden="true" />
      </Button>
    </form>
  )
}
