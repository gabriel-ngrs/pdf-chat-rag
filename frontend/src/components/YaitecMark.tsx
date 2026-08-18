/**
 * O "Y" da Yaitec.
 *
 * SVG inline, e não `<img>`, por uma razão concreta: o arquivo entregue pelo
 * owner (`Svg Yaitec.svg`, 538 kB) é um PNG de 1440 px embrulhado em SVG, com
 * fundo navy chapado. Servido como imagem ele seria um quadrado escuro no tema
 * claro e meio megabyte no cabeçalho. O traçado abaixo é o mesmo desenho
 * vetorizado a partir daquele arquivo — 1 kB, sem fundo, e pintado com
 * `currentColor`, que é o que o faz atravessar os dois temas sem dois arquivos.
 *
 * O desenho são três formas fechadas: a flâmula superior (as duas hastes que se
 * encontram no vértice) e as duas pernas que descem — na ordem em que saíram do
 * traçado, que é a ordem de área.
 *
 * Sem `<title>`: quem nomeia a marca é o texto acessível de quem a usa, e um
 * título aqui dentro somaria um segundo anúncio para a mesma coisa.
 */
export function YaitecMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 100 100"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <path d="M51.28 57.15 L48.58 57.02 L46.76 55.06 L18.29 12.96 L15.72 8.77 L15.52 7.35 L16.46 6.95 L19.30 6.68 L28.21 6.68 L29.96 6.82 L31.51 8.10 L40.01 20.38 L48.38 33.20 L48.52 34.14 L47.77 34.89 L42.91 35.29 L42.44 35.76 L44.20 38.87 L49.80 47.17 L50.27 47.10 L52.43 44.40 L57.83 35.90 L57.62 35.56 L56.68 35.29 L52.77 35.02 L51.75 34.14 L51.75 33.06 L68.89 7.69 L69.91 6.95 L72.47 6.68 L83.27 6.82 L85.09 7.42 L84.95 8.23 L84.01 9.72 L54.45 53.85 L52.70 56.28 L51.28 57.15 Z" />
      <path d="M46.56 93.32 L45.68 92.71 L39.61 83.54 L39.47 67.88 L38.93 66.53 L3.71 13.90 L0.47 8.91 L-0.07 7.83 L0.00 7.22 L1.35 6.82 L6.48 6.68 L7.42 6.95 L8.30 7.83 L46.63 64.91 L47.30 66.67 L47.30 91.36 L47.17 92.71 L46.56 93.32 Z" />
      <path d="M53.71 93.18 L53.24 92.85 L52.97 92.04 L53.10 66.40 L53.37 65.72 L91.43 8.50 L93.25 6.82 L97.44 6.68 L99.87 7.09 L100.07 8.10 L99.12 9.99 L61.34 66.80 L60.80 68.02 L60.80 83.13 L55.53 91.50 L53.71 93.18 Z" />
    </svg>
  )
}
