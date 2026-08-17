import { QuoteIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import type { Citation } from '@/lib/types'

/** Similaridade com vírgula decimal, como se escreve em pt-BR. */
function formatScore(score: number): string {
  return score.toFixed(2).replace('.', ',')
}

type CitationChipProps = {
  citation: Citation
}

/**
 * A prova de que a resposta veio do documento.
 *
 * O trecho **não** é recortado aqui: ele já chega em 240 caracteres, cortado em
 * fronteira de palavra pelo servidor. Recortar de novo no cliente arriscaria
 * mostrar menos do que foi de fato usado para responder.
 *
 * O diálogo vem do Radix porque foco, `Esc` e retorno do foco ao chip já vêm
 * resolvidos — refazer isso à mão é onde acessibilidade de modal costuma
 * quebrar.
 */
export function CitationChip({ citation }: CitationChipProps) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Badge
          asChild
          variant="outline"
          className="hover:bg-highlight hover:text-highlight-foreground focus-visible:bg-highlight focus-visible:text-highlight-foreground cursor-pointer transition-colors"
        >
          <button type="button" aria-label={`ver trecho da página ${citation.page_number}`}>
            <QuoteIcon aria-hidden="true" />
            página {citation.page_number}
          </button>
        </Badge>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Página {citation.page_number}</DialogTitle>
          <DialogDescription>
            Trecho do documento que sustentou esta parte da resposta.
          </DialogDescription>
        </DialogHeader>

        <blockquote className="border-highlight border-l-2 pl-4 text-body">
          {citation.snippet}
        </blockquote>

        <p className="text-muted-foreground tabular font-mono text-caption">
          similaridade {formatScore(citation.score)}
        </p>
      </DialogContent>
    </Dialog>
  )
}
