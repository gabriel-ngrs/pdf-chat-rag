---
spec: 01-ingestao-pdf
fase: B.1
slug_fase: design-system
tentativa: 1
veredito: APROVADO
score: 9.6
threshold: 8.5
range_avaliado: 26ba58610514ac27c86595b01ee657795d382c92..655c44fb5eb9640a6a376a439780d36e25dc5ccf
---

# FASE B.1 — Avaliação independente

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.6 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. As afirmações de contraste, teclado,
responsividade e alternância de tema foram **remedidas por mim** contra o
container, com script próprio, e batem com o relatório dentro de centésimos.

Ressalva de processo, sem efeito no veredito: a fase declara "Depende de:
nenhuma" e o `artefatos/` não existia no início — ela era, de fato, a única fase
do Track B elegível quando o executor começou (ARTIFACTS_SPEC §2.11.4). A
execução desta fase é a única do track que não fere a regra de elegibilidade.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | AC-23 remedido: 18 pares texto/fundo por tema × viewport, **zero reprovados**, pior 7,17 (claro) e 7,15 (escuro); `overflow_x = 0` a 375 px nos dois temas; 4 pontos de foco, todos `:focus-visible = true` e com nome acessível; toggle troca `documentElement.classList` (`antes:false → depois:true`) e o `aria-label` acompanha. Escopo travado: `grep` de hex/cor Tailwind crua fora de `ui/` = 0; sem biblioteca de estado global; `strict` intocado em `tsconfig.json`; nenhuma tela de upload/chat |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `components/` (apresentação) + `lib/` como a constitution do projeto exige; `AppShell.tsx` não importa nada de dados; `main.tsx:7-10` falha alto se `#root` sumir |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `grep -riE "GEMINI_API_KEY\|DATABASE_URL\|/home/gabriel\|api[_-]?key"` em `src/` = 0; `npm audit --audit-level=high` → `found 0 vulnerabilities`; `git diff 26ba586..e93a748 -- frontend/nginx.conf frontend/Dockerfile docker-compose.yml backend/` **vazio** — nenhum dos seis defeitos de §4.1 foi tocado |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Os 10 componentes de §4.7 vieram do CLI para `src/components/ui/` (`badge, button, card, dialog, progress, scroll-area, separator, skeleton, sonner, tooltip`); nenhum foi reescrito. `package.json` preexistente estendido, não substituído |
| 5 | Padrões de domínio/aplicação | 2 | 4 | Toda cor por token semântico; quatro degraus tipográficos + `--text-wordmark` como exceção declarada (`index.css:50-53`). Desconto: a escala de espaçamento é declarada em comentário (`index.css:35-36`) e o próprio código a fura em 5 pontos — ver §5 |
| 6 | Local e nomes dos arquivos | 2 | 5 | O diff bate 1:1 com "Arquivos novos"/"Arquivos alterados" da §5; `frontend/src/.gitkeep` removido como §4.9 manda |
| 7 | Qualidade de código | 2 | 5 | `tsc --noEmit` = 0, `eslint src` = 0, `npm run build` = 0. Comentários registram "por quê" (`index.css:20-40`, `AppShell.tsx:78-87`), nunca "o quê" — alinhado à constitution universal |
| 8 | Testes e cobertura | 2 | 4 | A fase não define teste unitário: define `tsc`/`lint` zero + verificação no container. Todos rodados por mim e verdes. Desconto porque a prova de AC-23 vive em script não versionado (re-executei o meu, mesmo resultado) |
| 9 | Migration safety (se aplicável) | 2 | — | Não se aplica: fase sem schema |

Média ponderada (dimensões 1–8, peso total 20): 96/20 = 4,8 → **9,6/10**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

1. **`frontend/src/index.css:35-36` — a escala de espaçamento declarada não é a
   que o código usa.** O comentário fixa "só nos degraus 1/2/3/4/6/8/12/16", e o
   código usa `py-10` e `py-14` (`AppShell.tsx:110`), `py-10`
   (`UploadDropzone.tsx:92`), `py-0.5` (`AppShell.tsx:63`) e `pt-0.5`
   (`App.tsx:82`). Nenhum quebra o DoD global ("espaçamento vem dos tokens do
   design system" — todos vêm da escala do Tailwind), mas o comentário é o
   contrato que o owner e a `FEAT-0002` vão seguir. Ou o comentário passa a
   listar `0.5/10/14`, ou os valores encostam em `1/8/12/16`.
2. **`AppShell.tsx:75` — `contentWidth: 'reading' | 'wide'` com `'wide'` sem
   nenhum uso.** É um parâmetro construído para a `FEAT-0002`. A constitution
   universal pede diff mínimo; se a `FEAT-0002` mudar de ideia sobre o layout do
   chat, isto vira código morto que ninguém remove.
3. **`--container-reading: 42rem` (`index.css:100`) diz "~72 caracteres".** Em
   IBM Plex Sans a 15 px, 672 px dão mais perto de 85 caracteres. O valor é
   confortável; o número no comentário é que está otimista.
4. **`src/components/ui/sonner.tsx:41` declara `classNames: { toast: "cn-toast" }`
   e a classe `cn-toast` não existe em lugar nenhum** (`grep` em `src/` e em
   `node_modules/shadcn/` = 0). É resíduo do preset. Sem efeito hoje —
   `Notices.tsx` sobrescreve `toastOptions` inteiro — mas é ruído no arquivo.

**Sobre as três dúvidas levantadas na §9 do relatório, minha leitura:**

- **`next-themes`:** concordo com o executor. O escopo travado proíbe
  "biblioteca de estado global" (Redux/Zustand/Jotai); um provider de preferência
  de apresentação, que entrou como dependência transitiva do `sonner` do próprio
  shadcn, não é isso. **Não é violação.** Reescrever `sonner.tsx` para removê-lo
  seria editar componente gerado por ganho nenhum.
- **`--text-wordmark` como quinto tamanho:** aceito. A regra da spec é "no máximo
  quatro tamanhos" para a **escala tipográfica de conteúdo**; um lockup de marca
  não é conteúdo, a exceção está declarada e comentada no lugar certo, e amarrar
  a marca à escala de corpo é de fato pior. **Não é violação.**
- **Verificação automatizada e não humana:** é o formato certo para um gate.
  Contraste "no olho" é justamente o que a skill `accessibility-audit` proíbe. O
  julgamento estético continua sendo do owner, como a spec previu (§5, passo 8).

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh .codeflow/specs/01-ingestao-pdf/SPEC_01_INGESTAO_PDF.md
✓ ids de fase únicos (10 fases)
✓ heading de cada fase casa com o bullet `id`
✓ todos os slugs são kebab-case
✓ wave: multi com ao menos um id `<TRACK>.<n>`
✓ todo `id` em "Depende de" existe na §5
✓ cada track tem 3–8 fases
✓ grafo de dependências acíclico
✓ §5 estruturalmente válida
EXIT=0

$ git merge-base --is-ancestor 655c44fb5eb9640a6a376a439780d36e25dc5ccf HEAD
655c44f... ancestor OK

$ cd frontend && npm ci
added 550 packages, and audited 551 packages in 8s
found 0 vulnerabilities

$ npx tsc --noEmit
tsc exit=0

$ npm run lint
> eslint src
lint exit=0

$ npm run build
dist/assets/index-ZbHVaq1E.css   47.64 kB │ gzip:   9.06 kB
dist/assets/index-Dp_eWz94.js   346.61 kB │ gzip: 109.06 kB
✓ built in 3.09s
build exit=0

$ npm audit --audit-level=high
found 0 vulnerabilities

# contraste / tema / overflow — script próprio do avaliador, contra o container
$ python3 audit2.py http://localhost:5173
 "desktop-light": {"classe_dark": false, "pares": 18, "reprovados": [], "pior": 7.17, "overflow_x": 0}
 "desktop-dark":  {"classe_dark": true,  "pares": 18, "reprovados": [], "pior": 7.15, "overflow_x": 0}
 "mobile-light":  {"classe_dark": false, "pares": 18, "reprovados": [], "pior": 7.17, "overflow_x": 0}
 "mobile-dark":   {"classe_dark": true,  "pares": 18, "reprovados": [], "pior": 7.15, "overflow_x": 0}
 "toggle_tema":   {"antes": false, "depois": true, "rotulo": "Mudar para o tema claro"}

# percurso de teclado (Tab a partir do topo, com um PDF já escolhido)
 1. a      "Pular para o conteúdo"    focusVisible=true  box-shadow oklch(0.58 0.16 62) 0 0 0 2px
 2. button "Mudar para o tema escuro" focusVisible=true  box-shadow oklab(0.58 .075 .141/.5) 0 0 0 3px
 3. input  (file, rotulado pelo label da dropzone) focusVisible=true
            label: border-color oklch(0.58 0.16 62) + ring 3px
 4. button "Enviar documento"         focusVisible=true  box-shadow oklab(0.58 .075 .141/.5) 0 0 0 3px

# escopo travado
$ grep -rnE "#[0-9a-fA-F]{3,8}\b|(text|bg|border|ring)-(slate|gray|...)-[0-9]" src --include=*.tsx | grep -v /ui/
(vazio)
$ grep -rniE "GEMINI_API_KEY|DATABASE_URL|/home/gabriel|api[_-]?key" src
(vazio)
$ git diff 26ba586..e93a748 -- frontend/nginx.conf frontend/Dockerfile docker-compose.yml backend/
(vazio)

$ git status --short
(vazio — árvore limpa ao final; dist/ e node_modules/ são ignorados)
```

**Nota metodológica:** minha primeira versão do script de contraste tratava
`background-color: rgba(0,0,0,0)` como preto opaco e reprovava o tema claro
inteiro. O defeito era do script, não da interface; corrigido (composição
correta de alpha) e re-rodado, o resultado é o da tabela acima. Registro porque
é exatamente o tipo de falso positivo que um avaliador precisa não propagar.

## 7. Itens da fase / DoD não atendidos

- **Gates de backend do `make check`** — `[—]` justificado e **confirmado por
  mim**: rodei `make check` nesta branch e ele falha em `arch` com
  `Could not find .importlinter`, arquivo que a `A.1` cria. `ruff`, `mypy`
  (4 arquivos), `eslint` e `tsc` passam. A falha é ausência da `A.1`, não desta
  fase. Correto marcar `[—]` (SPEC §3.10).
- Todo o resto da DoD da fase e do critério de conclusão está atendido e
  verificado.

## 8. Divergências entre o relatório e o código real

Nenhuma relevante. Confirmei ponto a ponto:

- "8 pares por tema/viewport, zero reprovados, pior 7,15" → medi 18 pares (meu
  walker é mais abrangente), zero reprovados, pior 7,15/7,17. **Confirma.**
- "toda cor vem de token semântico" → `grep` de hex e de cor Tailwind crua fora
  de `ui/` = 0. **Confirma.**
- "`Tab` alcança os dois controles" → alcança os dois na home vazia; com arquivo
  escolhido são quatro. **Confirma** (a diferença é o estado da tela, não o
  código).
- "nenhuma cor do preset sobreviveu" → `:root` e `.dark` em `index.css:106-209`
  redefinem todos os tokens de cor. **Confirma.**
