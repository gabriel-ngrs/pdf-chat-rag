import { ThemeProvider } from 'next-themes'

import { AppShell } from '@/components/AppShell'
import { Card, CardContent } from '@/components/ui/card'

const STEPS = [
  {
    title: 'Envie o PDF',
    description: 'Até 25 MB e 20 páginas. Nada sai da sua sessão neste navegador.',
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

function Home() {
  return (
    <div className="flex flex-col gap-12">
      <section className="flex flex-col gap-4">
        <h1 className="font-display text-display text-balance">Converse com o seu PDF.</h1>
        <p className="text-muted-foreground max-w-prose">
          Envie um documento e pergunte o que quiser sobre ele. O TalkDoc responde apenas com o que
          está escrito lá, e sempre diz de qual página tirou.
        </p>
      </section>

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
                  className="border-border flex items-start gap-4 px-4 py-4 not-last:border-b sm:px-6"
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
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      storageKey="talkdoc:theme"
      disableTransitionOnChange
    >
      <AppShell>
        <Home />
      </AppShell>
    </ThemeProvider>
  )
}
