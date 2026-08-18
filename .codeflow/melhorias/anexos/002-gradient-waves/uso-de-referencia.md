# Uso de referência entregue pelo owner

Instalação sugerida pela fonte (react-bits):

```
npx shadcn@latest add @react-bits/GradientWaves-JS-CSS
```

Uso:

```jsx
import GradientWaves from './GradientWaves';

<div style={{ width: '100%', height: '600px', position: 'relative' }}>
  <GradientWaves
    horizonColor="#5227FF"
    waveColor="#FF9FFC"
    crestColor="#FFFFFF"
    speed={0.4}
    amplitude={2.5}
    waveScale={0.6}
    waveRatio={0.9}
    swell={35}
    turbulence={20}
    tilt={1.11}
    zoom={1}
    height={5.5}
    fogDepth={15}
    detail="medium"
    brightness={1}
    opacity={1}
    mouseInteraction
    parallaxStrength={0.5}
    grain
    grainIntensity={0.05}
  />
</div>
```

As cores acima são as do exemplo original (roxo/rosa). A `MELH-002` discute por
que elas não entram como estão neste projeto.
