import { useEffect, useRef } from 'react'
import { Mesh, Program, Renderer, Triangle } from 'ogl'

import { prefersReducedMotion } from '@/hooks/useReducedMotion'
import type { Rgb } from '@/lib/colors'
import { cn } from '@/lib/utils'

/**
 * Campo de ondas em WebGL2, portado da referência entregue pelo owner na
 * MELH-002 (`.codeflow/melhorias/anexos/002-gradient-waves/`).
 *
 * O que mudou na porta, e por quê:
 *
 * - **Tipos.** O original é `.jsx` sem tipos. `tsc --strict` é regra da
 *   constitution, então props e uniforms são declarados.
 * - **Cores.** Os hex roxo/rosa do exemplo saíram. As três cores chegam de
 *   fora, já resolvidas a partir dos tokens do design system — é o que faz o
 *   fundo ser animado **e** continuar sendo este produto.
 * - **Movimento reduzido.** O `index.css` zera animação de CSS, e isto não é
 *   CSS: um `requestAnimationFrame` passa por baixo daquela regra. Quando a
 *   media query casa, o componente desenha **um** frame e não entra no laço.
 * - **Sem WebGL2.** No original, `new Renderer({ webgl: 2 })` lançando dentro
 *   do efeito derrubaria a árvore inteira. Aqui o construtor está sob
 *   `try/catch` e a falha deixa em cena o gradiente estático que já está no
 *   DOM por baixo do canvas.
 * - **Detalhe por tamanho de tela.** Menos passos de raymarching abaixo de
 *   640 px: é onde estão as GPUs que menos podem pagar 128 iterações por
 *   fragmento.
 *
 * O que veio da referência e sobreviveu de propósito: o laço para quando a aba
 * fica oculta e quando o elemento sai da viewport, e o `dpr` é limitado a 2.
 */

/** Passos de raymarching por fragmento. Menos passos, menos custo, menos nitidez. */
const STEPS_SMALL_SCREEN = 40
const STEPS_DEFAULT = 70
const SMALL_SCREEN_PX = 640

/**
 * Ajustes do campo de ondas, na sintonia entregue pelo owner.
 *
 * Ficam como constantes, e não como props, porque não há segunda chamada deste
 * componente com outra sintonia — e vinte props que ninguém passa são vinte
 * caminhos que ninguém testa.
 */
const TUNING = {
  speed: 0.4,
  amplitude: 2.5,
  waveScale: 0.6,
  waveRatio: 0.9,
  swell: 35,
  turbulence: 20,
  tilt: 1.11,
  zoom: 1,
  height: 5.5,
  fogDepth: 45,
  brightness: 1,
  opacity: 1,
  grainIntensity: 0.05,
  parallaxStrength: 0.5,
} as const

const vertex = `#version 300 es
in vec2 position;
void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`

const fragment = `#version 300 es
precision highp float;
uniform vec2 iResolution;
uniform float iTime;
uniform float uSpeed;
uniform float uAmplitude;
uniform float uWaveScale;
uniform float uWaveRatio;
uniform float uSwell;
uniform float uTurbulence;
uniform float uTilt;
uniform float uZoom;
uniform float uHeight;
uniform float uFogDepth;
uniform float uSteps;
uniform float uBrightness;
uniform float uOpacity;
uniform float uGrain;
uniform float uGrainIntensity;
uniform vec2 uMouse;
uniform float uParallax;
uniform bool uEnableMouse;
uniform vec3 uHorizonColor;
uniform vec3 uWaveColor;
uniform vec3 uCrestColor;
out vec4 fragColor;

const float MAX_DIST = 20000.0;

float hash21(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float plasma(vec3 r, vec2 freq, vec4 tc) {
  float mx = r.x + tc.x;
  mx += uSwell * sin((r.y + mx) / 20.0 + tc.y);
  float my = r.y - tc.z;
  my += uTurbulence * cos(r.x / 23.0 + tc.w);
  return r.z - (sin(mx * freq.x) * uAmplitude + sin(my * freq.y) * uAmplitude + uHeight);
}

float raymarch(vec3 pos, vec3 dir, vec2 freq, vec4 tc) {
  float dist = 0.0;
  for (int i = 0; i < 128; i++) {
    if (float(i) >= uSteps) break;
    float dscene = plasma(pos + dist * dir, freq, tc);
    if (abs(dscene) < 0.1) break;
    dist += 0.9 * dscene;
    if (!(abs(dist) < MAX_DIST)) return MAX_DIST;
  }
  return dist;
}

void main() {
  float T = iTime * uSpeed;
  vec2 freq = vec2(uWaveScale / 7.0, (uWaveScale * uWaveRatio) / 3.0);
  vec4 tc = vec4(T / 0.130, T / 0.810, T / 0.200, T / 0.710);
  float c, s;
  float vfov = (3.14159 / 2.3) / max(uZoom, 0.05);
  vec3 cam = vec3(0.0, 0.0, 30.0);
  vec2 uv = (gl_FragCoord.xy / iResolution.xy) - 0.5;
  uv.x *= iResolution.x / iResolution.y;
  uv.y *= -1.0;

  vec3 dir = vec3(0.0, 0.0, -1.0);
  float ulen = length(uv);
  float xrot = vfov * ulen;
  c = cos(xrot); s = sin(xrot);
  dir = mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c) * dir;
  vec2 nuv = ulen > 1e-5 ? uv / ulen : vec2(1.0, 0.0);
  c = nuv.x; s = nuv.y;
  dir = mat3(c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0) * dir;
  c = cos(uTilt); s = sin(uTilt);
  dir = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c) * dir;

  if (uEnableMouse) {
    float yaw = (uMouse.x - 0.5) * uParallax * 0.4;
    float pitch = (uMouse.y - 0.5) * uParallax * 0.4;
    c = cos(yaw); s = sin(yaw);
    dir = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c) * dir;
    c = cos(pitch); s = sin(pitch);
    dir = mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c) * dir;
  }

  float dist = raymarch(cam, dir, freq, tc);
  vec3 pos = cam + dist * dir;

  float t = clamp(uFogDepth / max(dist, 0.001), 0.0, 1.0);
  vec3 body = mix(uWaveColor, uCrestColor, clamp(pos.z * 0.08 + 0.5, 0.0, 1.0));
  vec3 col = mix(uHorizonColor, body, t);
  col *= uBrightness;
  col = clamp(col, 0.0, 1.0);

  float alpha = clamp(t, 0.0, 1.0) * uOpacity;
  if (uGrain > 0.5) {
    float g = hash21(gl_FragCoord.xy + mod(iTime, 64.0) * 11.0);
    alpha += (g - 0.5) * uGrainIntensity;
  }
  alpha = clamp(alpha, 0.0, 1.0);
  fragColor = vec4(col * alpha, alpha);
}
`

type GradientWavesProps = {
  /** Névoa do fundo: é nela que o campo se dissolve na distância. */
  horizonColor: Rgb
  /** Corpo da onda. */
  waveColor: Rgb
  /** Crista — o ponto mais alto, e o que carrega a cor da marca. */
  crestColor: Rgb
  className?: string
}

export function GradientWaves({
  horizonColor,
  waveColor,
  crestColor,
  className,
}: GradientWavesProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    let renderer: Renderer
    try {
      renderer = new Renderer({
        webgl: 2,
        alpha: true,
        premultipliedAlpha: true,
        antialias: false,
        dpr: Math.min(window.devicePixelRatio || 1, 2),
      })
    } catch {
      // Sem WebGL2 — navegador antigo, GPU bloqueada, aceleração desligada. O
      // gradiente estático de baixo continua sendo o fundo, e ninguém vê erro.
      return
    }

    const gl = renderer.gl
    gl.clearColor(0, 0, 0, 0)
    const canvas = gl.canvas
    canvas.style.width = '100%'
    canvas.style.height = '100%'
    canvas.style.display = 'block'
    container.appendChild(canvas)

    const steps = window.innerWidth < SMALL_SCREEN_PX ? STEPS_SMALL_SCREEN : STEPS_DEFAULT
    const reduced = prefersReducedMotion()

    const geometry = new Triangle(gl)
    const program = new Program(gl, {
      vertex,
      fragment,
      uniforms: {
        iTime: { value: 0 },
        iResolution: { value: new Float32Array([1, 1]) },
        uSpeed: { value: TUNING.speed },
        uAmplitude: { value: TUNING.amplitude },
        uWaveScale: { value: TUNING.waveScale },
        uWaveRatio: { value: TUNING.waveRatio },
        uSwell: { value: TUNING.swell },
        uTurbulence: { value: TUNING.turbulence },
        uTilt: { value: TUNING.tilt },
        uZoom: { value: TUNING.zoom },
        uHeight: { value: TUNING.height },
        uFogDepth: { value: TUNING.fogDepth },
        uSteps: { value: steps },
        uBrightness: { value: TUNING.brightness },
        uOpacity: { value: TUNING.opacity },
        // O grão é ruído redesenhado a cada frame. Num frame só ele seria uma
        // textura congelada e suja, então some junto com o movimento.
        uGrain: { value: reduced ? 0 : 1 },
        uGrainIntensity: { value: TUNING.grainIntensity },
        uMouse: { value: new Float32Array([0.5, 0.5]) },
        uParallax: { value: TUNING.parallaxStrength },
        uEnableMouse: { value: !reduced },
        uHorizonColor: { value: new Float32Array(horizonColor) },
        uWaveColor: { value: new Float32Array(waveColor) },
        uCrestColor: { value: new Float32Array(crestColor) },
      },
    })

    const mesh = new Mesh(gl, { geometry, program })

    const setSize = () => {
      const rect = container.getBoundingClientRect()
      renderer.setSize(Math.max(1, Math.floor(rect.width)), Math.max(1, Math.floor(rect.height)))
      const resolution = program.uniforms.iResolution.value as Float32Array
      resolution[0] = gl.drawingBufferWidth
      resolution[1] = gl.drawingBufferHeight
      renderer.render({ scene: mesh })
    }

    const resizeObserver = new ResizeObserver(setSize)
    resizeObserver.observe(container)
    setSize()

    if (reduced) {
      // Um frame, e acabou. Nenhum listener de ponteiro, nenhum laço, nenhum
      // observador de visibilidade — não há o que pausar.
      return () => {
        resizeObserver.disconnect()
        container.removeChild(canvas)
        gl.getExtension('WEBGL_lose_context')?.loseContext()
      }
    }

    const current: [number, number] = [0.5, 0.5]
    const target: [number, number] = [0.5, 0.5]

    const handlePointerMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      target[0] = (event.clientX - rect.left) / rect.width
      target[1] = 1 - (event.clientY - rect.top) / rect.height
    }
    const handlePointerLeave = () => {
      target[0] = 0.5
      target[1] = 0.5
    }
    canvas.addEventListener('pointermove', handlePointerMove)
    canvas.addEventListener('pointerleave', handlePointerLeave)

    let frame = 0
    let onScreen = true
    let pageVisible = !document.hidden
    const start = performance.now()

    const loop = (now: number) => {
      program.uniforms.iTime.value = (now - start) * 0.001
      // O ponteiro é perseguido, não seguido: 5% da diferença por frame é o que
      // transforma o salto do cursor em deriva.
      current[0] += 0.05 * (target[0] - current[0])
      current[1] += 0.05 * (target[1] - current[1])
      const mouse = program.uniforms.uMouse.value as Float32Array
      mouse[0] = current[0]
      mouse[1] = current[1]
      renderer.render({ scene: mesh })
      frame = requestAnimationFrame(loop)
    }

    const play = () => {
      if (onScreen && pageVisible && frame === 0) {
        frame = requestAnimationFrame(loop)
      }
    }
    const pause = () => {
      if (frame !== 0) {
        cancelAnimationFrame(frame)
        frame = 0
      }
    }

    const intersectionObserver = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting
        if (onScreen) {
          play()
        } else {
          pause()
        }
      },
      { threshold: 0 },
    )
    intersectionObserver.observe(container)

    const handleVisibility = () => {
      pageVisible = !document.hidden
      if (pageVisible) {
        play()
      } else {
        pause()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)

    play()

    return () => {
      pause()
      resizeObserver.disconnect()
      intersectionObserver.disconnect()
      document.removeEventListener('visibilitychange', handleVisibility)
      canvas.removeEventListener('pointermove', handlePointerMove)
      canvas.removeEventListener('pointerleave', handlePointerLeave)
      container.removeChild(canvas)
      gl.getExtension('WEBGL_lose_context')?.loseContext()
    }
  }, [horizonColor, waveColor, crestColor])

  return <div ref={containerRef} className={cn('relative size-full overflow-hidden', className)} />
}
