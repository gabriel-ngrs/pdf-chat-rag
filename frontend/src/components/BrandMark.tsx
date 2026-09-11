/**
 * A marca do TalkDoc.
 *
 * O desenho é o produto em três traços: uma folha com o canto dobrado e, dentro
 * dela, o retângulo cheio do marca-texto. É o mesmo gesto que a interface faz no
 * chat — a resposta vem, e o trecho que a sustenta fica marcado no documento.
 *
 * SVG inline, e não `<img>`: pintado com `currentColor`, um único desenho
 * atravessa os dois temas sem dois arquivos e sem um quadrado de fundo chapado.
 *
 * Sem `<title>`: quem nomeia a marca é o wordmark ao lado, e um título aqui
 * dentro somaria um segundo anúncio para a mesma coisa.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {/* A folha, com o canto superior direito cortado pela dobra. */}
      <path
        d="M6.75 2.5h7.25L19 7.5v12.25a1.75 1.75 0 0 1-1.75 1.75H6.75A1.75 1.75 0 0 1 5 19.75V4.25A1.75 1.75 0 0 1 6.75 2.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      {/* A dobra: a mesma diagonal, vista por dentro. */}
      <path
        d="M14 2.5v3.25a1.75 1.75 0 0 0 1.75 1.75H19"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      {/* O marca-texto sobre a linha citada. */}
      <rect x="8" y="12.75" width="8" height="4.5" rx="1" fill="currentColor" />
    </svg>
  )
}
