/** Cor em sRGB, cada canal de 0 a 1 — que é como um shader e um canvas a querem. */
export type Rgb = readonly [number, number, number]

/**
 * Traduz um valor de cor CSS para os três canais de sRGB.
 *
 * O caminho é o canvas, e não uma conversão escrita à mão, porque os tokens
 * deste projeto estão em `oklch` — e converter oklch para sRGB à mão significa
 * carregar as duas matrizes do Oklab, a curva de transferência e o recorte de
 * gamut, tudo para chegar ao mesmo número que o navegador já sabe calcular. O
 * canvas aceita qualquer cor que o CSS aceite, então basta pintar um pixel e
 * ler de volta.
 *
 * Devolve `null` quando não há canvas (jsdom) ou quando o valor não é uma cor
 * que o navegador reconheça. Quem chama decide o que fazer com isso — aqui não
 * há cor de reserva, porque uma cor de reserva escondida neste módulo seria
 * exatamente o hex fora do design system que o `index.css` proíbe.
 */
export function cssColorToRgb(value: string): Rgb | null {
  const trimmed = value.trim()
  if (trimmed === '') {
    return null
  }

  const canvas = document.createElement('canvas')
  canvas.width = 1
  canvas.height = 1
  const context = canvas.getContext('2d')
  if (!context) {
    return null
  }

  // Atribuir um `fillStyle` inválido é ignorado em silêncio pelo canvas: o
  // valor anterior fica. O sentinela é o que transforma esse silêncio em
  // resposta — se depois da atribuição o estilo continua sendo ele, a cor não
  // foi entendida.
  const sentinel = '#000000'
  context.fillStyle = sentinel
  context.fillStyle = trimmed
  if (context.fillStyle === sentinel && trimmed !== sentinel) {
    return null
  }

  context.fillRect(0, 0, 1, 1)
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data
  return [r / 255, g / 255, b / 255]
}

/**
 * Lê um token do design system e devolve os canais de sRGB.
 *
 * O nome é o da custom property (`--highlight`), sem `var()`: quem resolve a
 * cascata é o `getComputedStyle` sobre o elemento raiz, que é onde os dois
 * temas do projeto definem os seus valores.
 */
export function readTokenRgb(token: string): Rgb | null {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(token)
  return cssColorToRgb(raw)
}
