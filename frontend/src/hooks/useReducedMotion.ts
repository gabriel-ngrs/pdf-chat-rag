import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

/**
 * A pessoa pediu movimento reduzido?
 *
 * O `index.css` já zera duração e atraso de animação para quem pede — mas essa
 * regra é CSS, e CSS não alcança um `requestAnimationFrame`, um listener de
 * `mousemove` nem a decisão de aplicar uma classe de animação. Tudo que se move
 * por JS neste projeto passa por aqui.
 *
 * O valor inicial é `false` em vez de ser lido no primeiro render porque o
 * mesmo componente renderiza no jsdom, onde `matchMedia` pode não existir: a
 * consulta acontece dentro do efeito, que só roda no navegador. Assumir "não
 * reduzir" antes de saber é o erro certo — a alternativa faria a interface
 * inteira nascer sem movimento e ganhá-lo um frame depois.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      return
    }
    const media = window.matchMedia(QUERY)
    setReduced(media.matches)

    const handleChange = (event: MediaQueryListEvent) => setReduced(event.matches)
    media.addEventListener('change', handleChange)
    return () => media.removeEventListener('change', handleChange)
  }, [])

  return reduced
}

/**
 * A mesma pergunta, fora do React.
 *
 * Serve a quem precisa decidir **antes** de montar qualquer coisa — um canvas
 * que só deve desenhar um frame, por exemplo. Devolve `false` quando
 * `matchMedia` não existe, pela mesma razão do hook acima.
 */
export function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(QUERY).matches
}
