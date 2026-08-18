import { GradientWaves } from '@/components/backgrounds/GradientWaves'
import { ShapeGrid } from '@/components/backgrounds/ShapeGrid'
import { useTokenColors } from '@/hooks/useTokenColors'

/**
 * Qual fundo a tela usa.
 *
 * `waves` é a entrada — a tela de envio, onde o texto é curto e o efeito faz o
 * trabalho de primeira impressão. `grid` é a conversa, onde o fundo precisa
 * existir sem disputar com o que está sendo lido.
 */
export type BackgroundKind = 'waves' | 'grid'

/**
 * As três cores do shader, e de onde vêm.
 *
 * A referência do owner trazia roxo e rosa fixos. Aqui elas saem dos tokens,
 * que é o que faz o fundo ser animado **e** continuar sendo este produto: a
 * névoa é o fundo da página, o corpo da onda é o azul da Yaitec, e a crista
 * brilha na cor do marca-texto.
 */
const WAVE_TOKENS = ['--background', '--primary', '--highlight'] as const

/** A malha da conversa é desenhada na mesma cor das bordas do sistema. */
const GRID_TOKENS = ['--border'] as const

/**
 * O fundo mora onde o texto não mora.
 *
 * Os dois fundos são recortados pela mesma ideia, e ela é o que resolve o
 * critério de aceite mais duro da MELH-002 de forma estrutural em vez de
 * caso a caso: em vez de auditar cada pedaço de texto para ver se tem
 * superfície por baixo, o fundo é apagado na área onde o texto vive. O que
 * sobra é o efeito emoldurando a coluna de leitura pelas margens.
 *
 * A medida do recorte é `46rem` porque a coluna é `--container-reading`, de
 * `42rem`: quatro rem de folga de cada lado. Em tela estreita a elipse cobre a
 * viewport inteira e o fundo desaparece — que é o certo, porque ali não há
 * margem onde ele pudesse aparecer sem ficar atrás de texto.
 *
 * A transição é longa de propósito. Máscara radial com parada dura deixa um
 * anel visível, e um anel é mais chamativo que o efeito que ele recorta.
 */
const READING_COLUMN_MASK =
  'radial-gradient(ellipse 46rem 38rem at 50% 42%, transparent 45%, black 100%)'

/**
 * O fundo da tela, atrás de tudo.
 *
 * A camada é `fixed` e negativa no eixo z: ela não entra no fluxo, não rola com
 * o conteúdo e não recebe ponteiro. O cabeçalho e o rodapé têm superfície
 * própria com desfoque, e a coluna de leitura vive sobre cards — nenhum texto
 * da interface fica direto sobre o shader, que é o critério de aceite mais
 * duro da MELH-002: o fundo muda de cor a cada frame, e contraste medido uma
 * vez sobre ele não valeria para o frame seguinte.
 *
 * Enquanto os tokens não puderam ser lidos, fica só o gradiente estático — ele
 * é também o que se vê quando não há WebGL2, e é por isso que está no DOM
 * mesmo quando o canvas está.
 */
export function AppBackground({ kind }: { kind: BackgroundKind }) {
  const waveColors = useTokenColors(kind === 'waves' ? WAVE_TOKENS : [])
  const gridColors = useTokenColors(kind === 'grid' ? GRID_TOKENS : [])

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {kind === 'waves' ? (
        <div
          className="absolute inset-0"
          style={{ maskImage: READING_COLUMN_MASK, WebkitMaskImage: READING_COLUMN_MASK }}
        >
          {/* Degradação sem WebGL2, e cor de espera enquanto o shader compila.
              As paradas saem dos mesmos tokens do shader, então a troca de uma
              coisa pela outra não é uma troca de paleta. */}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_85%_55%_at_50%_115%,color-mix(in_oklab,var(--highlight)_30%,transparent),color-mix(in_oklab,var(--primary)_12%,transparent)_45%,transparent_75%)]" />
          {waveColors.length === WAVE_TOKENS.length ? (
            <div className="absolute inset-0 opacity-90">
              <GradientWaves
                horizonColor={waveColors[0]}
                waveColor={waveColors[1]}
                crestColor={waveColors[2]}
              />
            </div>
          ) : null}
          {/* Véu leve sobre o shader: quem garante o contraste é o recorte,
              não ele. O que este véu faz é puxar o campo inteiro na direção do
              fundo da página, para o efeito parecer parte da tela em vez de
              um vídeo colado atrás dela. */}
          <div className="bg-background/25 absolute inset-0" />
        </div>
      ) : null}

      {kind === 'grid' && gridColors.length === GRID_TOKENS.length ? (
        <div
          className="absolute inset-0"
          style={{ maskImage: READING_COLUMN_MASK, WebkitMaskImage: READING_COLUMN_MASK }}
        >
          <ShapeGrid color={gridColors[0]} opacity={0.4} />
        </div>
      ) : null}
    </div>
  )
}
