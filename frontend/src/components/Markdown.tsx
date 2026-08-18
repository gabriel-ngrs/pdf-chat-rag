import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { cn } from '@/lib/utils'

/**
 * O mínimo de um nó de mdast que este módulo precisa conhecer.
 *
 * Escrito à mão em vez de importado de `@types/mdast`: aquele pacote chega aqui
 * como dependência transitiva do `react-markdown`, e depender do que não está
 * no `package.json` é o tipo de acoplamento que quebra num `npm install` de
 * amanhã.
 */
type MdastNode = {
  type: string
  value?: string
  children?: MdastNode[]
}

/**
 * Transforma HTML cru do modelo em texto literal.
 *
 * O conteúdo vem de um modelo que leu um PDF de origem desconhecida, então
 * renderizar HTML dali seria abrir XSS pela porta da frente. Sem `rehype-raw`,
 * o `react-markdown` já não executa nada — mas ele **descarta** as marcas, e
 * uma resposta que dissesse "use a tag `<script>`" apareceria mutilada, sem
 * sinal de que algo sumiu.
 *
 * Este plugin troca o tipo do nó de `html` para `text`, preservando o valor. O
 * resultado é o que a MELH-001 pede: a marca aparece escrita na tela, e nunca
 * como elemento. Blocos de código não são afetados — ali o texto já chega como
 * `code`, e não como `html`.
 */
function remarkHtmlAsText() {
  return (tree: unknown) => {
    const visit = (node: MdastNode) => {
      if (node.type === 'html') {
        node.type = 'text'
      }
      node.children?.forEach(visit)
    }
    visit(tree as MdastNode)
  }
}

/**
 * Mapa de elementos → tokens do design system.
 *
 * Nenhuma classe de tamanho ou de cor sai da escala declarada no `index.css`: a
 * biblioteca não traz estilo próprio, e é aqui que se garante que ela não passe
 * a trazer.
 */
const components: Components = {
  // Títulos são rebaixados a texto forte de propósito. Um `<h2>` no meio da
  // lista de mensagens entraria na árvore de cabeçalhos da página e um leitor
  // de tela passaria a navegar por dentro da resposta como se fosse seção.
  h1: ({ children }) => <p className="font-semibold">{children}</p>,
  h2: ({ children }) => <p className="font-semibold">{children}</p>,
  h3: ({ children }) => <p className="font-semibold">{children}</p>,
  h4: ({ children }) => <p className="font-semibold">{children}</p>,
  h5: ({ children }) => <p className="font-semibold">{children}</p>,
  h6: ({ children }) => <p className="font-semibold">{children}</p>,

  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,

  ul: ({ children }) => <ul className="list-disc space-y-1.5 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1.5 pl-5">{children}</ol>,

  a: ({ children, href }) => (
    // `noreferrer` cobre `noopener` nos navegadores atuais e ainda impede que o
    // destino saiba de onde o clique veio. O `href` já chega higienizado: o
    // `react-markdown` derruba `javascript:` e afins por padrão.
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="decoration-border hover:decoration-current underline underline-offset-2"
    >
      {children}
    </a>
  ),

  code: ({ children, className }) => {
    // O `react-markdown` só marca a linguagem no bloco cercado; sem classe é
    // código inline, que não pode virar bloco no meio de uma frase.
    const isBlock = typeof className === 'string' && className.includes('language-')
    if (isBlock) {
      return <code className="font-mono text-caption">{children}</code>
    }
    return (
      <code className="bg-muted rounded-sm px-1 py-0.5 font-mono text-[0.9em]">{children}</code>
    )
  },

  pre: ({ children }) => (
    <pre className="bg-muted overflow-x-auto rounded-md p-3">{children}</pre>
  ),

  blockquote: ({ children }) => (
    // A mesma barra âncora do trecho citado no diálogo de citação: dentro deste
    // produto, uma barra na cor do marca-texto significa "isto veio do papel".
    <blockquote className="border-highlight text-muted-foreground border-l-2 pl-4">
      {children}
    </blockquote>
  ),

  hr: () => <hr className="border-border" />,

  // A tabela é o único conteúdo que pode ser mais largo que a coluna de
  // leitura. Ela rola dentro do próprio contêiner — a página, não.
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-caption">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-border border-b px-2 py-1.5 text-left font-medium">{children}</th>
  ),
  td: ({ children }) => <td className="border-border border-b px-2 py-1.5 align-top">{children}</td>,
}

/**
 * `img` fica de fora porque uma imagem numa resposta significaria o navegador
 * buscando uma URL escolhida por quem escreveu o PDF — vazamento de IP e de
 * momento de leitura, em troca de nada que o produto precise mostrar.
 */
const DISALLOWED = ['img']

type MarkdownProps = {
  children: string
  className?: string
}

/**
 * A resposta do modelo, renderizada.
 *
 * O Gemini formata em Markdown mesmo quando não se pede, e até a MELH-001 a
 * interface imprimia a string crua — os asteriscos apareciam na tela. Aqui a
 * sintaxe vira estrutura, e a estrutura vira os tokens do design system.
 *
 * O `space-y-3` no contêiner é o que dá hierarquia ao bloco: sem ele a resposta
 * é uma parede de mil e duzentos caracteres. A largura de leitura continua com
 * quem chama.
 */
export function Markdown({ children, className }: MarkdownProps) {
  return (
    <div className={cn('space-y-3', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkHtmlAsText]}
        disallowedElements={DISALLOWED}
        // Redundante com a ausência do `rehype-raw`, e é para ser: a garantia
        // de que HTML do documento nunca vira elemento não pode depender de
        // alguém lembrar por que um plugin **não** está na lista.
        skipHtml
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
