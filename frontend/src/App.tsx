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

/**
 * Os três passos, em uma linha de três colunas.
 *
 * Empilhados eles custavam 292 px — o maior bloco da tela de entrada, para
 * dizer o que a interface logo abaixo já demonstra. A descrição encolheu junto
 * com a largura: em coluna de ~200 px, a frase de antes ocupava cinco linhas.
 *
 * O que foi cortado é o que o rodapé já diz com as mesmas palavras ("fica nesta
 * sessão do navegador", "toda resposta cita a página"). O que ficou é o que não
 * está em nenhum outro lugar da tela: que a leitura leva alguns segundos, e que
 * "não achei" é uma resposta possível.
 */
const STEPS = [
  {
    title: 'Envie o PDF',
    description: 'Fica só nesta sessão do navegador.',
  },
  {
    title: 'Aguarde a leitura',
    description: 'Alguns segundos para virar trechos consultáveis.',
  },
  {
    title: 'Pergunte',
    description: 'A resposta cita a página — ou diz que não achou.',
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
    <section className="flex flex-col gap-3" aria-labelledby="como-funciona">
      <h2
        id="como-funciona"
        className="text-muted-foreground font-mono text-caption tracking-widest uppercase"
      >
        Como funciona
      </h2>
      <Card className="py-0">
        <CardContent className="px-0">
          {/* Empilhado abaixo de `sm`, onde três colunas dariam ~110 px cada e
              a descrição quebraria a cada duas palavras. O divisor acompanha:
              horizontal quando é lista, vertical quando é linha. */}
          <ol className="grid sm:grid-cols-3">
            {STEPS.map((step, index) => (
              <li
                key={step.title}
                // Hover por superfície e borda, e não por sombra: o sistema tem
                // uma sombra só, e ela é de elemento flutuante. `transition-colors`
                // não toca em geometria, então a lista não se mexe.
                className="border-border hover:bg-accent/40 flex items-start gap-3 px-4 py-3.5 transition-colors duration-150 not-last:border-b sm:px-5 sm:not-last:border-r sm:not-last:border-b-0"
              >
                <span
                  className="text-muted-foreground tabular pt-0.5 font-mono text-caption"
                  aria-hidden="true"
                >
                  {String(index + 1).padStart(2, '0')}
                </span>
                <div className="flex flex-col gap-0.5">
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
      <div className="flex flex-col gap-6 sm:gap-8">
        {/* A abertura ganhou superfície própria na MELH-002. Sobre o campo de
            ondas, texto solto ficaria sobre uma cor que muda a cada frame — e
            contraste medido uma vez ali não valeria para o frame seguinte. O
            card é opaco por isso, e não por estilo. */}
        <section
          className={cn(
            'border-border bg-card flex flex-col gap-3 rounded-xl border p-5 sm:p-6',
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
