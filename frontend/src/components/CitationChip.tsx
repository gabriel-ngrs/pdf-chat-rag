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
 * Um dos trechos que o servidor consultou para montar a resposta.
 *
 * O rótulo diz **consultado**, e não "usado": o backend emite os trechos que
 * passaram do limiar de similaridade, que é um conjunto maior do que aquele em
 * que a resposta de fato se apoiou (BUG-003). Prometer "esta é a fonte desta
 * frase" seria mentira verificável — quem abrisse o segundo chip veria um
 * trecho sem relação com o que leu.
 *
 * O trecho **não** é recortado aqui: ele já chega em 240 caracteres, cortado em
 * fronteira de palavra pelo servidor. Recortar de novo no cliente arriscaria
 * mostrar menos do que foi de fato consultado.
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
          <button
            type="button"
            aria-label={`ver trecho consultado da página ${citation.page_number}`}
          >
            <QuoteIcon aria-hidden="true" />
            página {citation.page_number}
          </button>
        </Badge>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Trecho consultado · página {citation.page_number}</DialogTitle>
          <DialogDescription>
            Um dos trechos do documento que o TalkDoc consultou para responder. Nem todo
            trecho consultado aparece na resposta.
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
