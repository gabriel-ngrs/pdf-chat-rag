import { useRef } from 'react'
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

/**
 * Progresso derivado do que o backend informou, sem deixar a barra andar para
 * trás: uma resposta atrasada chegando fora de ordem não pode desfazer na tela
 * um avanço que o usuário já viu.
 */
function useMonotonicPercent(document: DocumentDetail | null): number | null {
  const highest = useRef(0)
  const percent = progressPercent(document)

  if (percent === null) {
    return null
  }
  highest.current = Math.max(highest.current, percent)
  return highest.current
}

export function ProcessingStatus({ documentId, onReset }: ProcessingStatusProps) {
  const { document, missing, loading } = useDocumentStatus(documentId)
  const percent = useMonotonicPercent(document)

  if (missing) {
    const { title, message, action } = describeError('nao_encontrado')
    return (
      <StatusCard
        icon={<TriangleAlertIcon className="text-destructive size-4" aria-hidden="true" />}
        title={title}
        description={`${message} ${action}`}
        onReset={onReset}
        resetLabel="Enviar outro documento"
      />
    )
  }

  if (!document) {
    return (
      <Card>
        <CardContent className="flex flex-col gap-3" aria-busy={loading}>
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-full" />
        </CardContent>
      </Card>
    )
  }

  const { title, description } = LABELS[document.status]
  const inProgress = document.status === 'pending' || document.status === 'processing'

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            {/* Mudança de estado anunciada para leitor de tela: quem não vê a
                barra precisa saber que o documento ficou pronto. */}
            <p className="flex items-center gap-2 text-body font-medium" role="status">
              {document.status === 'ready' ? (
                <CheckIcon className="text-success size-4" aria-hidden="true" />
              ) : null}
              {document.status === 'failed' ? (
                <TriangleAlertIcon className="text-destructive size-4" aria-hidden="true" />
              ) : null}
              {title}
            </p>
            <p className="text-muted-foreground text-caption break-words">
              {document.status === 'failed'
                ? (document.error_message ??
                  'O servidor não explicou o motivo. Tente enviar o arquivo de novo.')
                : description}
            </p>
          </div>
          {document.status === 'ready' ? (
            <Badge variant="secondary">Pronto para conversar</Badge>
          ) : null}
        </div>

        <p className="text-muted-foreground tabular font-mono text-caption break-all">
          {document.filename}
          {document.page_count ? ` · ${document.page_count} páginas` : ''}
        </p>

        {inProgress ? (
          percent === null ? (
            // Janela legítima de indeterminação: o total de trechos ainda não
            // existe, então não há porcentagem a mostrar.
            <Skeleton className="h-1 w-full rounded-full" />
          ) : (
            <div className="flex flex-col gap-2">
              <Progress
                value={percent}
                aria-label="Progresso da leitura do documento"
                // `aria-valuenow` e `aria-valuetext` explícitos: o primitivo
                // desenha a barra mas não estava expondo o valor, e uma barra
                // sem valor não diz nada a quem usa leitor de tela.
                aria-valuenow={percent}
                aria-valuetext={`${document.chunks_processed} de ${document.chunks_total} trechos`}
              />
              <p className="text-muted-foreground tabular font-mono text-caption">
                {document.chunks_processed} de {document.chunks_total} trechos · {percent}%
              </p>
            </div>
          )
        ) : null}

        {document.status === 'failed' ? (
          <div className="flex justify-end">
            <Button size="lg" onClick={onReset}>
              Enviar outro documento
            </Button>
          </div>
        ) : null}

        {document.status === 'ready' ? (
          <div className="flex justify-end">
            <Button size="lg" variant="outline" onClick={onReset}>
              Enviar outro documento
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function StatusCard({
  icon,
  title,
  description,
  onReset,
  resetLabel,
}: {
  icon: ReactNode
  title: string
  description: string
  onReset: () => void
  resetLabel: string
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <p className="flex items-center gap-2 text-body font-medium" role="status">
            {icon}
            {title}
          </p>
          <p className="text-muted-foreground text-caption">{description}</p>
        </div>
        <div className="flex justify-end">
          <Button size="lg" onClick={onReset}>
            {resetLabel}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
