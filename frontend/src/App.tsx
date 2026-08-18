import { useCallback, useEffect, useState } from 'react'
import { ThemeProvider } from 'next-themes'

import { AppShell } from '@/components/AppShell'
import { ChatView, forgetConversation } from '@/components/ChatView'
import { Notices } from '@/components/Notices'
import { ProcessingStatus } from '@/components/ProcessingStatus'
import { UploadDropzone } from '@/components/UploadDropzone'
import { Card, CardContent } from '@/components/ui/card'
import { useNotices } from '@/hooks/useNotices'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { loadConfig } from '@/lib/config'
import type { ConfigState } from '@/lib/config'
import type { DocumentDetail, UploadAccepted } from '@/lib/types'
import { cn } from '@/lib/utils'

/** O documento em acompanhamento sobrevive a um recarregamento da página. */
const DOCUMENT_STORAGE_KEY = 'talkdoc:document-id'

const STEPS = [
  {
    title: 'Envie o PDF',
    description: 'Nada sai da sua sessão neste navegador.',
  },
  {
    title: 'Acompanhe a leitura',
    description:
      'O documento é lido página a página e transformado em trechos consultáveis. Isso leva alguns segundos.',
  },
  {
    title: 'Pergunte',
    description: 'A resposta vem com a página de onde foi tirada — ou com um "não encontrei".',
  },
]

/**
 * Carrega os limites do servidor uma vez, no boot.
 *
 * Falha aqui não trava o app: vira estado degradado e um aviso. Quem recusa o
 * arquivo passa a ser o servidor, que é quem sempre teve a palavra final.
 */
function useAppConfig(): ConfigState {
  const notify = useNotices()
  const [state, setState] = useState<ConfigState>({ status: 'loading' })

  useEffect(() => {
    let active = true
    void loadConfig().then((loaded) => {
      if (!active) {
        return
      }
      setState(loaded)
      if (loaded.status === 'degraded') {
        notify.error(loaded.code, {
          message: 'Não consegui ler do servidor os limites de envio.',
        })
      }
    })
    return () => {
      active = false
    }
  }, [notify])

  return state
}

function HowItWorks() {
  return (
    <section className="flex flex-col gap-4" aria-labelledby="como-funciona">
      <h2
        id="como-funciona"
        className="text-muted-foreground font-mono text-caption tracking-widest uppercase"
      >
        Como funciona
      </h2>
      <Card className="py-0">
        <CardContent className="px-0">
          <ol>
            {STEPS.map((step, index) => (
              <li
                key={step.title}
                // Hover por superfície e borda, e não por sombra: o sistema tem
                // uma sombra só, e ela é de elemento flutuante. `transition-colors`
                // não toca em geometria, então a lista não se mexe.
                className="border-border hover:bg-accent/40 flex items-start gap-4 px-4 py-4 transition-colors duration-150 not-last:border-b sm:px-6"
              >
                <span
                  className="text-muted-foreground tabular pt-0.5 font-mono text-caption"
                  aria-hidden="true"
                >
                  {String(index + 1).padStart(2, '0')}
                </span>
                <div className="flex flex-col gap-1">
                  <h3 className="text-body font-medium">{step.title}</h3>
                  <p className="text-muted-foreground text-caption">{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </section>
  )
}

function TalkDoc() {
  const notify = useNotices()
  const config = useAppConfig()
  const reducedMotion = useReducedMotion()
  const [documentId, setDocumentId] = useState<string | null>(null)
  const [readyDocument, setReadyDocument] = useState<DocumentDetail | null>(null)

  useEffect(() => {
    setDocumentId(localStorage.getItem(DOCUMENT_STORAGE_KEY))
  }, [])

  const handleAccepted = useCallback(
    (accepted: UploadAccepted) => {
      localStorage.setItem(DOCUMENT_STORAGE_KEY, accepted.id)
      setDocumentId(accepted.id)
      notify.success('Documento recebido. Começando a leitura.')
    },
    [notify],
  )

  const handleReset = useCallback(() => {
    localStorage.removeItem(DOCUMENT_STORAGE_KEY)
    forgetConversation()
    setDocumentId(null)
    setReadyDocument(null)
  }, [])

  // O acompanhamento entrega o documento pronto e sai de cena: é o gancho que
  // leva do processamento à conversa sem que ninguém precise clicar em nada.
  const handleReady = useCallback((document: DocumentDetail) => {
    setReadyDocument(document)
  }, [])

  if (readyDocument) {
    return (
      <AppShell background="grid">
        <ChatView document={readyDocument} onReset={handleReset} />
      </AppShell>
    )
  }

  return (
    <AppShell background="waves">
      <div className="flex flex-col gap-12">
        {/* A abertura ganhou superfície própria na MELH-002. Sobre o campo de
            ondas, texto solto ficaria sobre uma cor que muda a cada frame — e
            contraste medido uma vez ali não valeria para o frame seguinte. O
            card é opaco por isso, e não por estilo. */}
        <section
          className={cn(
            'border-border bg-card flex flex-col gap-4 rounded-xl border p-6 sm:p-8',
            !reducedMotion && 'animate-rise',
          )}
        >
          <h1 className="font-display text-display text-balance">Converse com o seu PDF.</h1>
          <p className="text-muted-foreground max-w-prose">
            Envie um documento e pergunte o que quiser sobre ele. O TalkDoc responde apenas com o
            que está escrito lá, e sempre diz de qual página tirou.
          </p>
        </section>

        {documentId ? (
          <ProcessingStatus documentId={documentId} onReset={handleReset} onReady={handleReady} />
        ) : (
          <UploadDropzone
            limits={config.status === 'ready' ? config.limits : null}
            onAccepted={handleAccepted}
          />
        )}

        <HowItWorks />
      </div>
    </AppShell>
  )
}

export default function App() {
  return (
    <ThemeProvider
      attribute="class"
      // Escuro por padrão desde a MELH-002. O `index.html` aplica o mesmo
      // padrão antes da primeira pintura — mudar um sem o outro traz o piscar
      // de volta.
      defaultTheme="dark"
      enableSystem
      storageKey="talkdoc:theme"
      disableTransitionOnChange
    >
      <TalkDoc />
      <Notices />
    </ThemeProvider>
  )
}
