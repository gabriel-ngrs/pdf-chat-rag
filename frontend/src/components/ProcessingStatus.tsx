import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { CheckIcon, TriangleAlertIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { progressPercent, useDocumentStatus } from '@/hooks/useDocumentStatus'
import { describeError } from '@/lib/errors'
import type { DocumentDetail } from '@/lib/types'

type ProcessingStatusProps = {
  documentId: string
  /** Volta para a tela de envio, descartando o documento em acompanhamento. */
  onReset: () => void
  /**
   * Avisa que o documento ficou pronto, entregando o que o servidor informou.
   *
   * É por aqui que se sai do acompanhamento para a conversa. Quem consulta o
   * servidor continua sendo só este componente: com a tela de chat consultando
   * por conta própria, seriam duas rodadas de polling para a mesma resposta.
   */
  onReady?: (document: DocumentDetail) => void
}

const LABELS: Record<DocumentDetail['status'], { title: string; description: string }> = {
  pending: {
    title: 'Na fila',
    description: 'O arquivo chegou. A leitura começa em instantes.',
  },
  processing: {
    title: 'Lendo o documento',
    description: 'Cada página vira trechos consultáveis. Isso leva alguns segundos.',
  },
  ready: {
    title: 'Pronto',
    description: 'O documento está indexado e pode ser consultado.',
  },
  failed: {
    title: 'Não deu para processar',
    description: '',
  },
}

type View = {
  title: string
  description: string
  icon: ReactNode
  showReset: boolean
  /** Em `failed` a ação é o próximo passo óbvio; em `ready` é alternativa. */
  resetVariant: 'default' | 'outline'
}

function resolveView(doc: DocumentDetail | null, missing: boolean): View {
  if (missing) {
    const { title, message, action } = describeError('nao_encontrado')
    return {
      title,
      description: `${message} ${action}`,
      icon: <TriangleAlertIcon className="text-destructive size-4" aria-hidden="true" />,
      showReset: true,
      resetVariant: 'default',
    }
  }

  if (!doc) {
    return {
      title: 'Verificando o documento',
      description: 'Buscando o estado no servidor.',
      icon: null,
      showReset: false,
      resetVariant: 'outline',
    }
  }

  const { title, description } = LABELS[doc.status]

  if (doc.status === 'failed') {
    return {
      title,
      description:
        doc.error_message ?? 'O servidor não explicou o motivo. Tente enviar o arquivo de novo.',
      icon: <TriangleAlertIcon className="text-destructive size-4" aria-hidden="true" />,
      showReset: true,
      resetVariant: 'default',
    }
  }

  return {
    title,
    description,
    icon:
      doc.status === 'ready' ? (
        <CheckIcon className="text-success size-4" aria-hidden="true" />
      ) : null,
    showReset: doc.status === 'ready',
    resetVariant: 'outline',
  }
}

/**
 * Progresso derivado do que o backend informou, sem deixar a barra andar para
 * trás: uma resposta atrasada chegando fora de ordem não pode desfazer na tela
 * um avanço que o usuário já viu.
 */
function useMonotonicPercent(doc: DocumentDetail | null): number | null {
  const highest = useRef(0)
  const percent = progressPercent(doc)

  if (percent === null) {
    return null
  }
  highest.current = Math.max(highest.current, percent)
  return highest.current
}

/**
 * Acompanhamento do processamento.
 *
 * O card é sempre o mesmo elemento, do primeiro render ao estado terminal: uma
 * live region recém-inserida no DOM costuma não ser anunciada, e remontá-la na
 * transição do esqueleto para o conteúdo faria a primeira mudança de estado
 * passar em silêncio para quem usa leitor de tela.
 */
export function ProcessingStatus({ documentId, onReset, onReady }: ProcessingStatusProps) {
  const { document: doc, missing, loading } = useDocumentStatus(documentId)
  const percent = useMonotonicPercent(doc)

  useEffect(() => {
    if (doc?.status === 'ready') {
      onReady?.(doc)
    }
  }, [doc, onReady])
  const view = resolveView(doc, missing)
  const inProgress = doc?.status === 'pending' || doc?.status === 'processing'

  return (
    <Card>
      <CardContent className="flex flex-col gap-4" aria-busy={loading}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1">
            <p className="flex items-center gap-2 text-body font-medium" role="status">
              {view.icon}
              {view.title}
            </p>
            <p className="text-muted-foreground text-caption break-words">{view.description}</p>
          </div>
          {doc?.status === 'ready' ? (
            <Badge variant="secondary">Pronto para conversar</Badge>
          ) : null}
        </div>

        {doc ? (
          <p className="text-muted-foreground tabular font-mono text-caption break-all">
            {doc.filename}
            {doc.page_count ? ` · ${doc.page_count} páginas` : ''}
          </p>
        ) : (
          <Skeleton className="h-3 w-48" />
        )}

        {inProgress && doc ? (
          percent === null ? (
            // Janela legítima de indeterminação: o total de trechos ainda não
            // existe, então não há porcentagem a mostrar.
            <Skeleton className="h-1 w-full rounded-full" />
          ) : (
            <div className="flex flex-col gap-2">
              <Progress
                value={percent}
                aria-label="Progresso da leitura do documento"
                // `aria-valuenow` vem do primitivo. O `aria-valuetext` fica
                // porque "8 de 12 trechos" diz mais a quem ouve do que "67%".
                aria-valuetext={`${doc.chunks_processed} de ${doc.chunks_total} trechos`}
              />
              <p className="text-muted-foreground tabular font-mono text-caption">
                {doc.chunks_processed} de {doc.chunks_total} trechos · {percent}%
              </p>
            </div>
          )
        ) : null}

        {view.showReset ? (
          <div className="flex justify-end">
            <Button size="lg" variant={view.resetVariant} onClick={onReset}>
              Enviar outro documento
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
