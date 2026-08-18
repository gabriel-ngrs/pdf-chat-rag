import { useEffect, useRef } from 'react'

import { useReducedMotion } from '@/hooks/useReducedMotion'

/**
 * Um halo que segue o ponteiro dentro de um elemento.
 *
 * É a leitura defensável de "animações de mouse" da MELH-004: um efeito, num
 * lugar só — o card de envio. Dentro da conversa seria ruído sobre o texto que
 * a pessoa está lendo, e cursor customizado está descartado por quebrar
 * affordance.
 *
 * O movimento acontece em duas custom properties, e não em posição de
 * elemento: escrever `--spotlight-x` repinta o gradiente do `::after` sem
 * invalidar layout, enquanto mover um elemento de verdade a cada `pointermove`
 * cobraria layout da árvore inteira, em cima de uma lista que já rola sozinha.
 * A regra do `::after` mora no `index.css`, sob `.pointer-spotlight`.
 *
 * Duas portas fechadas antes de qualquer listener:
 * - `prefers-reduced-motion`, que nenhuma regra de CSS alcançaria aqui;
 * - `pointer: coarse`, porque em toque o "ponteiro" só existe durante o toque —
 *   o halo acenderia sob o dedo, no lugar que o dedo está tapando.
 */
export function usePointerSpotlight<T extends HTMLElement>() {
  const reducedMotion = useReducedMotion()
  const ref = useRef<T>(null)

  useEffect(() => {
    const element = ref.current
    if (!element || reducedMotion) {
      return
    }
    if (typeof window.matchMedia === 'function' && !window.matchMedia('(pointer: fine)').matches) {
      return
    }

    const handleMove = (event: PointerEvent) => {
      const rect = element.getBoundingClientRect()
      element.style.setProperty('--spotlight-x', `${event.clientX - rect.left}px`)
      element.style.setProperty('--spotlight-y', `${event.clientY - rect.top}px`)
      element.style.setProperty('--spotlight-opacity', '1')
    }
    const handleLeave = () => {
      element.style.setProperty('--spotlight-opacity', '0')
    }

    element.addEventListener('pointermove', handleMove)
    element.addEventListener('pointerleave', handleLeave)
    return () => {
      element.removeEventListener('pointermove', handleMove)
      element.removeEventListener('pointerleave', handleLeave)
      // O halo não pode sobreviver ao efeito: sem os listeners, uma opacidade
      // esquecida em 1 congelaria a luz no último lugar por onde o ponteiro
      // passou.
      element.style.removeProperty('--spotlight-opacity')
    }
  }, [reducedMotion])

  return {
    ref,
    /** Vazio sob movimento reduzido — sem a classe, o `::after` não existe. */
    className: reducedMotion ? undefined : 'pointer-spotlight',
  }
}
