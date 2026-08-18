import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { useTheme } from 'next-themes'
import { MoonIcon, QuoteIcon, ShieldCheckIcon, SunIcon } from 'lucide-react'

import { AppBackground } from '@/components/backgrounds/AppBackground'
import type { BackgroundKind } from '@/components/backgrounds/AppBackground'
import { YaitecMark } from '@/components/YaitecMark'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

/**
 * Alternador de tema.
 *
 * Só renderiza o ícone depois de montado porque o tema resolvido vem do
 * localStorage e do `prefers-color-scheme`: desenhar antes disso mostraria o
 * ícone errado por um instante.
 */
function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const isDark = resolvedTheme === 'dark'
  const label = isDark ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          aria-label={label}
          className="rounded-full"
          onClick={() => setTheme(isDark ? 'light' : 'dark')}
        >
          {mounted ? (
            isDark ? (
              <SunIcon aria-hidden="true" />
            ) : (
              <MoonIcon aria-hidden="true" />
            )
          ) : (
            <span className="size-4" />
          )}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

/**
 * Marca do produto.
 *
 * Sans bold com "Doc" no azul da Yaitec, como no mockup de 2026-08-18. Antes
 * era Instrument Serif com o "Doc" dentro de um chip da cor do marca-texto —
 * a mesma cor que marca a citação no chat, o que amarrava a marca ao que o
 * produto faz. O lockup ficou mais direto e menos particular; a ligação com a
 * citação passou a ser só a cor, sem o gesto do chip.
 *
 * `tracking-tight` porque em 21 px e peso 700 o Plex abre demais entre as
 * letras e o lockup deixa de ler como uma palavra só.
 */
function Wordmark() {
  return (
    <span className="text-wordmark leading-none font-bold tracking-tight">
      Talk<span className="text-primary">Doc</span>
    </span>
  )
}

/**
 * O lockup do cabeçalho: o produto, um fio, e quem o assina.
 *
 * A hierarquia é a informação. Duas marcas do mesmo tamanho brigariam e a
 * página deixaria de dizer qual é o produto — daí o "Y" da Yaitec vir menor que
 * o wordmark e em `text-muted-foreground`, subindo para o primeiro plano só no
 * hover. A separação é um fio de 1 px na cor de borda porque é assim que este
 * sistema resolve profundidade: por traço, não por sombra.
 */
function Lockup() {
  return (
    <div className="flex items-center gap-3">
      <Wordmark />
      <span aria-hidden="true" className="bg-border h-5 w-px" />
      <a
        href="https://yaitec.com"
        target="_blank"
        rel="noreferrer"
        aria-label="por Yaitec — abrir o site em nova aba"
        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring rounded-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
      >
        <YaitecMark className="size-5" />
      </a>
    </div>
  )
}

type AppShellProps = {
  children: ReactNode
  /**
   * O fundo da tela (MELH-002). Sem valor, não há camada nenhuma — que é o que
   * deve acontecer em qualquer tela nova enquanto ninguém decidiu o contrário.
   */
  background?: BackgroundKind
  /**
   * `reading` mantém a coluna em ~72 caracteres, que é o limite confortável de
   * leitura. `wide` existe para o chat da FEAT-0002, onde a conversa e as
   * citações convivem lado a lado.
   */
  contentWidth?: 'reading' | 'wide'
}

/**
 * Casca da aplicação: cabeçalho fixo, área de conteúdo com largura legível e
 * rodapé discreto.
 *
 * O grid de três linhas garante que o rodapé fique no fim da viewport mesmo com
 * pouco conteúdo, sem depender de altura fixa.
 */
export function AppShell({ children, contentWidth = 'reading', background }: AppShellProps) {
  // Cabeçalho, conteúdo e rodapé compartilham a mesma coluna: sem isso a marca
  // flutua numa margem e o conteúdo em outra, e a página perde o eixo.
  const column = cn(
    'mx-auto w-full px-4 sm:px-6',
    contentWidth === 'reading' ? 'max-w-reading' : 'max-w-5xl',
  )

  return (
    <TooltipProvider>
      {background ? <AppBackground kind={background} /> : null}

      <div className="grid min-h-dvh grid-rows-[auto_1fr_auto]">
        <a
          href="#main-content"
          className="bg-primary text-primary-foreground focus-visible:ring-ring sr-only rounded-md px-3 py-2 focus-visible:not-sr-only focus-visible:absolute focus-visible:top-2 focus-visible:left-2 focus-visible:z-50 focus-visible:ring-2"
        >
          Pular para o conteúdo
        </a>

        <header className="border-border bg-background/90 sticky top-0 z-40 border-b backdrop-blur-sm">
          <div className={cn(column, 'flex h-14 items-center justify-between gap-4')}>
            <Lockup />
            <ThemeToggle />
          </div>
        </header>

        {/* `min-h-0` deixa o conteúdo encolher dentro da linha `1fr` do grid,
            que é o que permite uma tela pedir `h-full` e ocupar exatamente o
            que sobra — sem ninguém precisar saber de cor quanto a casca mede. */}
        <main id="main-content" className={cn(column, 'min-h-0 py-5 sm:py-6')}>
          {children}
        </main>

        <footer className="border-border bg-background/90 border-t backdrop-blur-sm">
          {/* As duas garantias do produto, com o disco de ícone preenchido do
              mockup. Ficaram no rodapé, e não num card no fim da página como
              lá: o mockup dizia as mesmas duas frases duas vezes — uma no card
              e outra no rodapé — e a tela precisa caber sem rolagem.

              O texto foi encurtado até caber em uma linha dentro da coluna de
              leitura. Alargar só o rodapé resolveria a quebra e quebraria outra
              coisa: cabeçalho, conteúdo e rodapé dividem a mesma coluna, e é
              isso que dá eixo à página. */}
          <div
            className={cn(
              column,
              'text-muted-foreground flex flex-col gap-3 py-3 text-caption sm:flex-row sm:items-center sm:justify-between sm:gap-6',
            )}
          >
            <p className="flex items-center gap-2.5">
              <span className="bg-primary/15 text-primary flex size-7 shrink-0 items-center justify-center rounded-full">
                <QuoteIcon className="size-3.5" aria-hidden="true" />
              </span>
              Toda resposta cita a página de origem.
            </p>
            <p className="flex items-center gap-2.5">
              <span className="bg-primary/15 text-primary flex size-7 shrink-0 items-center justify-center rounded-full">
                <ShieldCheckIcon className="size-3.5" aria-hidden="true" />
              </span>
              Seus documentos ficam nesta sessão.
            </p>
          </div>
        </footer>
      </div>
    </TooltipProvider>
  )
}
