import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { useTheme } from 'next-themes'
import { MoonIcon, SunIcon } from 'lucide-react'

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
          variant="ghost"
          size="icon"
          aria-label={label}
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
 * O marca-texto sobre "Doc" é a identidade inteira em um gesto: é o que o
 * produto faz com o documento — marcar o trecho que responde à pergunta.
 */
function Wordmark() {
  return (
    <span className="font-display text-wordmark leading-none tracking-normal">
      Talk
      <span className="bg-highlight text-highlight-foreground rounded-xs px-1 py-0.5">Doc</span>
    </span>
  )
}

type AppShellProps = {
  children: ReactNode
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
export function AppShell({ children, contentWidth = 'reading' }: AppShellProps) {
  // Cabeçalho, conteúdo e rodapé compartilham a mesma coluna: sem isso a marca
  // flutua numa margem e o conteúdo em outra, e a página perde o eixo.
  const column = cn(
    'mx-auto w-full px-4 sm:px-6',
    contentWidth === 'reading' ? 'max-w-reading' : 'max-w-5xl',
  )

  return (
    <TooltipProvider>
      <div className="grid min-h-dvh grid-rows-[auto_1fr_auto]">
        <a
          href="#main-content"
          className="bg-primary text-primary-foreground focus-visible:ring-ring sr-only rounded-md px-3 py-2 focus-visible:not-sr-only focus-visible:absolute focus-visible:top-2 focus-visible:left-2 focus-visible:z-50 focus-visible:ring-2"
        >
          Pular para o conteúdo
        </a>

        <header className="border-border bg-background/90 sticky top-0 z-40 border-b backdrop-blur-sm">
          <div className={cn(column, 'flex h-14 items-center justify-between gap-4')}>
            <Wordmark />
            <ThemeToggle />
          </div>
        </header>

        <main id="main-content" className={cn(column, 'py-10 sm:py-14')}>
          {children}
        </main>

        <footer className="border-border border-t">
          <div
            className={cn(
              column,
              'text-muted-foreground flex flex-col gap-1 py-6 text-caption sm:flex-row sm:items-center sm:justify-between',
            )}
          >
            <p>Toda resposta cita a página do PDF de onde veio.</p>
            <p>Seus documentos ficam nesta sessão do navegador.</p>
          </div>
        </footer>
      </div>
    </TooltipProvider>
  )
}
