import { useEffect, useState } from 'react'

import { readTokenRgb } from '@/lib/colors'
import type { Rgb } from '@/lib/colors'

/**
 * As cores de um conjunto de tokens, relidas quando o tema muda.
 *
 * Existe porque os fundos da MELH-002 desenham em canvas — e um canvas não
 * herda `var(--highlight)`: ele quer três números. Sem este hook, a única saída
 * seria escrever hex dentro do componente, que é o que o `index.css` proíbe em
 * primeira linha, e o fundo ficaria com a cor do tema claro depois de alternar
 * para o escuro.
 *
 * O gatilho é a classe `dark` no `<html>`, escrita pelo `next-themes`. Um
 * `MutationObserver` sobre esse atributo é mais direto do que assinar o tema
 * pelo React: quem desenha são componentes de fundo espalhados, e todos querem
 * saber a mesma coisa — que a cascata mudou.
 *
 * Enquanto os tokens não puderam ser lidos (jsdom, ou o primeiro render antes
 * do CSS aplicar), a lista vem vazia. Quem chama trata isso como "ainda não
 * dá para desenhar", que é a verdade — e não como preto.
 */
export function useTokenColors(tokens: readonly string[]): Rgb[] {
  const key = tokens.join(' ')
  const [colors, setColors] = useState<Rgb[]>([])

  useEffect(() => {
    const read = () => {
      const resolved = key
        .split(' ')
        .map(readTokenRgb)
        .filter((color): color is Rgb => color !== null)
      // Tudo ou nada: uma lista pela metade faria o chamador casar cor com
      // posição errada, e um fundo com as cores trocadas é pior que nenhum.
      setColors(resolved.length === key.split(' ').length ? resolved : [])
    }

    read()

    if (typeof MutationObserver !== 'function') {
      return
    }
    const observer = new MutationObserver(read)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [key])

  return colors
}
