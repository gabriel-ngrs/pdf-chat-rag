import { useEffect, useRef } from 'react'

import type { Rgb } from '@/lib/colors'
import { cn } from '@/lib/utils'

/**
 * Malha de quadrados desenhada uma vez, portada do `ShapeGrid` entregue pelo
 * owner na MELH-002.
 *
 * **Estático foi o pedido, e é também a única forma defensável aqui.** Este
 * fundo fica atrás da conversa — atrás do texto que a pessoa está lendo com
 * atenção. A referência original faz a malha derivar na diagonal a 60 fps e
 * acende a célula sob o ponteiro; as duas coisas competem com a leitura, e a
 * primeira ainda cobraria GPU durante todo o tempo que alguém passa lendo uma
 * resposta. Sem laço, o custo é um `drawRect` por célula por redimensionamento,
 * e `prefers-reduced-motion` não tem o que reduzir: não há movimento.
 *
 * O que sobrou da referência: a malha, o tamanho de célula, e o fato de ser
 * canvas. O que saiu: o `requestAnimationFrame`, o `IntersectionObserver`, o
 * `visibilitychange`, o rastro de hover e as opacidades por célula — tudo isso
 * existia para servir a um laço que não existe mais.
 */

/** Lado da célula, em pixels de CSS. */
const DEFAULT_CELL_PX = 40

type ShapeGridProps = {
  /** Cor do traço da malha, já resolvida a partir de um token. */
  color: Rgb
  /** Opacidade do traço. A malha é textura de fundo, não conteúdo. */
  opacity?: number
  cellSize?: number
  className?: string
}

export function ShapeGrid({
  color,
  opacity = 1,
  cellSize = DEFAULT_CELL_PX,
  className,
}: ShapeGridProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }
    const context = canvas.getContext('2d')
    if (!context) {
      // jsdom não tem contexto 2d, e um navegador com canvas desligado também
      // não. Nos dois casos o fundo simplesmente não existe — que é o pior que
      // pode acontecer com uma textura decorativa.
      return
    }

    const [r, g, b] = color
    const stroke = `rgb(${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)})`

    const draw = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const width = Math.max(1, Math.floor(rect.width))
      const height = Math.max(1, Math.floor(rect.height))

      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)
      // Desenhar em unidades de CSS e deixar a escala com o contexto: sem isto
      // a malha teria o dobro da densidade num monitor retina.
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      context.clearRect(0, 0, width, height)

      // O meio pixel alinha o traço de 1 px ao pixel físico. Sem ele, cada
      // linha cai entre dois pixels e sai borrada nos dois.
      context.translate(0.5, 0.5)
      context.strokeStyle = stroke
      context.globalAlpha = opacity
      context.lineWidth = 1

      context.beginPath()
      for (let x = 0; x <= width; x += cellSize) {
        context.moveTo(x, 0)
        context.lineTo(x, height)
      }
      for (let y = 0; y <= height; y += cellSize) {
        context.moveTo(0, y)
        context.lineTo(width, y)
      }
      context.stroke()
    }

    draw()

    const observer = new ResizeObserver(draw)
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [color, opacity, cellSize])

  return <canvas ref={canvasRef} aria-hidden="true" className={cn('block size-full', className)} />
}
