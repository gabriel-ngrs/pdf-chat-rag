import { useId, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import { CloudUploadIcon, FileTextIcon, Loader2Icon, UploadIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useNotices } from '@/hooks/useNotices'
import { usePointerSpotlight } from '@/hooks/usePointerSpotlight'
import { formatFileSize, useUpload, validateSelection } from '@/hooks/useUpload'
import type { AppConfig, UploadAccepted } from '@/lib/types'
import { cn } from '@/lib/utils'

type UploadDropzoneProps = {
  /** `null` quando `GET /api/config` falhou: sem limites conhecidos, quem recusa é o servidor. */
  limits: AppConfig | null
  onAccepted: (accepted: UploadAccepted) => void
}

/**
 * Tela de envio do PDF.
 *
 * A área de soltar é o `<label>` de um `<input type="file">` real e focável: é o
 * que faz arrastar, clicar e navegar por teclado levarem ao mesmo lugar, sem
 * `div` fingindo ser controle.
 */
export function UploadDropzone({ limits, onAccepted }: UploadDropzoneProps) {
  const notify = useNotices()
  const { state, send } = useUpload()
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [selected, setSelected] = useState<File | null>(null)
  const [draggingOver, setDraggingOver] = useState(false)
  const spotlight = usePointerSpotlight<HTMLDivElement>()

  const sending = state.status === 'sending'

  function selectFile(file: File | undefined) {
    if (!file) {
      return
    }
    const problem = validateSelection(file, limits)
    if (problem) {
      notify.error(problem.code, { message: problem.message })
      setSelected(null)
      if (inputRef.current) {
        inputRef.current.value = ''
      }
      return
    }
    setSelected(file)
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0])
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDraggingOver(false)
    if (sending) {
      return
    }
    selectFile(event.dataTransfer.files[0])
  }

  /**
   * O botão principal muda de trabalho conforme o estado.
   *
   * Sem arquivo escolhido ele abre o seletor; com arquivo, envia. Antes ele
   * nascia desabilitado, e a tela de entrada abria com a sua ação principal
   * apagada — o mockup mostra um CTA azul vivo porque desenha o estado com
   * arquivo já escolhido, e copiar a aparência sem copiar o estado deixaria a
   * primeira impressão sendo um botão morto.
   *
   * A área tracejada continua fazendo as duas coisas (clicar e arrastar): duas
   * portas para o seletor é o padrão de qualquer upload, não ambiguidade.
   */
  function handlePrimary() {
    if (!selected) {
      inputRef.current?.click()
      return
    }
    void handleSend()
  }

  async function handleSend() {
    if (!selected) {
      return
    }
    const accepted = await send(selected)
    if (accepted) {
      onAccepted(accepted)
    }
  }

  const limitsLabel = limits
    ? `PDF de até ${limits.max_upload_mb} MB e ${limits.max_pdf_pages} páginas.`
    : 'PDF. Os limites serão conferidos pelo servidor.'

  return (
    <Card ref={spotlight.ref} className={spotlight.className}>
      <CardContent className="flex flex-col gap-3">
        <div
          onDragOver={(event) => {
            event.preventDefault()
            setDraggingOver(true)
          }}
          onDragLeave={(event) => {
            // `dragleave` borbulha: entrar num filho dispara o evento no pai e
            // apagaria o destaque no meio do arraste.
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              setDraggingOver(false)
            }
          }}
          onDrop={handleDrop}
        >
          <label
            htmlFor={inputId}
            className={cn(
              // 120 ms e `transition-[color,background-color,border-color,transform]`:
              // o arraste precisa de resposta imediata, e a escala de 1% é o
              // limite entre "a área reagiu" e "a página pulou". `transform`
              // não invalida layout, então o card ao lado não se move junto.
              // `border-input` pelo mesmo motivo do campo de pergunta: o
              // retângulo tracejado é o controle, e com `--border` ele saía a
              // 1,3:1 contra o branco do card — a principal affordance da tela
              // de entrada quase sem contorno.
              // Tracejado azul do mockup no lugar do cinza de controle. A
              // opacidade é diferente por tema porque o contraste é: sobre o
              // branco do card, `primary/55` dá 1,8:1 e reprovaria a 1.4.11 do
              // WCAG, que pede 3:1 para o contorno que identifica um controle.
              // Sobre a tinta do escuro, a mesma opacidade dá 4,4:1.
              'border-primary/90 dark:border-primary/60 flex cursor-pointer flex-col items-center gap-2.5 rounded-lg border border-dashed px-6 py-4 text-center transition-[color,background-color,border-color,transform] duration-150 ease-out',
              'has-[input:focus-visible]:border-ring has-[input:focus-visible]:ring-ring/50 has-[input:focus-visible]:ring-3',
              draggingOver && 'border-ring bg-accent scale-[1.01]',
              sending && 'pointer-events-none opacity-60',
            )}
          >
            {/* O input vive DENTRO do label: é o que faz `:has(input:focus-visible)`
                casar e a área de soltar mostrar foco quando alguém chega nela
                pelo teclado — de fora, o seletor nunca casaria. */}
            <input
              ref={inputRef}
              id={inputId}
              type="file"
              accept="application/pdf,.pdf"
              className="sr-only"
              disabled={sending}
              onChange={handleInputChange}
            />
            {selected ? (
              <>
                <span
                  className="icon-halo bg-primary/12 text-primary flex size-12 items-center justify-center rounded-full"
                  aria-hidden="true"
                >
                  <FileTextIcon className="size-5" />
                </span>
                <span className="flex flex-col gap-1">
                  <span className="text-body font-medium break-all">{selected.name}</span>
                  <span className="text-muted-foreground tabular font-mono text-caption">
                    {formatFileSize(selected.size)}
                  </span>
                </span>
                <span className="text-muted-foreground text-caption">
                  Clique ou arraste outro arquivo para trocar.
                </span>
              </>
            ) : (
              <>
                {/* Disco com halo, do mockup. O halo é decorativo e mora no
                    `index.css`: não é a sombra do sistema, é foco. */}
                <span
                  className="icon-halo bg-primary/12 text-primary flex size-12 items-center justify-center rounded-full"
                  aria-hidden="true"
                >
                  <CloudUploadIcon className="size-6" />
                </span>
                <span className="flex flex-col gap-1">
                  {/* "clique para escolher" em azul, como no mockup. É texto
                      dentro do `<label>`, e não um link: o alvo clicável é a
                      área inteira, e um `<a>` aqui prometeria uma navegação que
                      não existe. A cor marca onde o clique leva, e o `<label>`
                      já dá o comportamento a quem usa teclado. */}
                  <span className="text-body font-medium">
                    Arraste um PDF aqui ou{' '}
                    <span className="text-primary">clique para escolher</span>
                  </span>
                  <span className="text-muted-foreground text-caption">{limitsLabel}</span>
                </span>
              </>
            )}
          </label>
        </div>

        {/* O botão fica FORA da área tracejada, e isso não é estética.
            Aquela área é um `<label>` que embrulha o `<input type="file">`:
            um `<button>` dentro dela teria o clique capturado pelo label e
            abriria o seletor de arquivo em vez de enviar. O mockup o desenha
            por dentro; por dentro ele não funcionaria. */}
        <div className="flex flex-col items-center gap-3">
          {sending ? (
            // Indicador indeterminado de propósito: `fetch` não reporta bytes
            // enviados, então uma porcentagem aqui seria inventada.
            <span
              className="text-muted-foreground flex items-center gap-2 text-caption"
              role="status"
            >
              <Loader2Icon className="size-3.5 animate-spin" aria-hidden="true" />
              Enviando o arquivo…
            </span>
          ) : null}
          <Button
            size="lg"
            // O gradiente do mockup, nas duas paradas que o sistema já tem: a
            // cor de repouso e a de hover. No hover as duas viram a de hover,
            // então o botão escurece inteiro em vez de o gradiente inverter.
            // No desabilitado as duas viram `muted`, senão a imagem de fundo
            // cobriria o `disabled:bg-muted` da variante e o rótulo ficaria
            // ilegível — só que aqui desabilitado passou a ser exceção, e não
            // o estado de partida.
            className="from-primary to-primary-hover hover:from-primary-hover disabled:from-muted disabled:to-muted w-full bg-linear-to-b sm:w-auto sm:min-w-56"
            disabled={sending}
            onClick={handlePrimary}
          >
            <UploadIcon aria-hidden="true" />
            {selected ? 'Enviar documento' : 'Escolher arquivo'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
