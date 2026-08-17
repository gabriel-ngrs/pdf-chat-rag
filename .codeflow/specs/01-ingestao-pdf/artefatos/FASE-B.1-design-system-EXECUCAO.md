---
spec: 01-ingestao-pdf
fase: B.1
slug_fase: design-system
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: 26ba58610514ac27c86595b01ee657795d382c92
sha_final: 655c44fb5eb9640a6a376a439780d36e25dc5ccf
range: 26ba58610514ac27c86595b01ee657795d382c92..655c44fb5eb9640a6a376a439780d36e25dc5ccf
---

# FASE B.1 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/Yaitec-TalkDoc-trackB`, branch
> `feat/trackB-frontend`, criada a partir de `dev` (`26ba586`) porque os agentes
> do Track A trabalham em paralelo em `feat/trackA-ingestao`.

## 1. Resumo do que foi feito

O frontend saiu de "pasta vazia com configuração" para uma casca servida em
container, com design system próprio. shadcn/ui foi inicializado sobre Radix
(base `radix`, preset `nova`) e os dez componentes de §4.7 foram copiados para
`src/components/ui/`. Sobre as variáveis OKLCH que o CLI gera, foi definido o
sistema do projeto: paleta de papel/tinta com um âmbar de marca-texto, quatro
degraus tipográficos, três famílias com trabalhos distintos, raio único e escala
de espaçamento declarada. A `AppShell` traz cabeçalho fixo com marca e
alternador de tema, coluna de leitura de ~72 caracteres, rodapé e link de pular
para o conteúdo.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `frontend/index.html` | Documento raiz em pt-BR; aplica o tema salvo antes da primeira pintura para a página não piscar no tema errado |
| `frontend/components.json` | Configuração do CLI do shadcn (base `radix`, preset `nova`, alias `@`) |
| `frontend/eslint.config.js` | Flat config com `typescript-eslint` e `react-hooks` |
| `frontend/src/main.tsx` | Monta o `App` em `#root` |
| `frontend/src/App.tsx` | `ThemeProvider` + casca + conteúdo da home (hero e "como funciona") |
| `frontend/src/index.css` | **O design system**: tokens, escalas e temas, com o porquê de cada decisão em comentário |
| `frontend/src/lib/utils.ts` | `cn()` (gerado pelo CLI) |
| `frontend/src/components/AppShell.tsx` | Casca: cabeçalho, coluna de conteúdo, rodapé, alternador de tema, skip link |
| `frontend/src/components/ui/*.tsx` | `button`, `card`, `progress`, `scroll-area`, `separator`, `skeleton`, `sonner`, `tooltip`, `badge`, `dialog` — copiados pelo CLI |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `frontend/tsconfig.json` | `baseUrl` + `paths` para o alias `@` — pré-requisito do CLI do shadcn. `strict` intocado |
| `frontend/vite.config.ts` | `resolve.alias` do `@`; proxy e servidor preservados |
| `frontend/package.json` | Dependências do shadcn (`radix-ui`, `sonner`, `lucide-react`, `class-variance-authority`, `tailwind-merge`, `tw-animate-css`, `next-themes`, `shadcn`) e as três famílias de `@fontsource` |
| `frontend/package-lock.json` | Recommitado após o CLI, como a spec previa (risco 5) |
| `frontend/src/.gitkeep` | Removido — a pasta ganhou conteúdo (§4.9) |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `Dockerfile`, `nginx.conf`, `.dockerignore`, o `proxy` do
`vite.config.ts`, o `strict` do `tsconfig.json` e o `docker-compose.yml` foram
mantidos intactos — nenhum dos seis defeitos de §4.1 foi tocado. O
`package.json` preexistente (React 19, Vite 6, Tailwind 4, eslint 9) foi
estendido, não reescrito.

**Contexto declarado antes de escolher estética** (skill `avoid-ai-look`, passo 1):
público = quem envia um PDF de trabalho e precisa confiar na resposta; tom =
sóbrio, técnico, documental; metáfora = papel e tinta, com o âmbar do
marca-texto como cor de marca.

**Sinais de "cara de IA" evitados, com a troca deliberada que entrou no lugar:**

| Sinal | O que entrou no lugar |
|---|---|
| Fonte default do preset (Geist) em tudo | IBM Plex Sans na interface, IBM Plex Mono nos números que o usuário compara, Instrument Serif só na marca e no H1 |
| Gradiente/roxo de enfeite | Uma cor de marca (âmbar de marca-texto) + neutros; nenhum gradiente |
| Card dentro de card empilhado | Um card único com linhas separadas por hairline — lê como documento, não como painel |
| Sombra genérica em tudo | Profundidade por hierarquia (peso, tamanho, espaço) e 1px de borda; sombra reservada a elemento flutuante |
| Cinza neutro morto | Fundo claro levemente quente (hue 85) e escuro levemente azul — os dois temas têm temperatura própria |
| Tudo centralizado | Coluna única alinhada à esquerda, com cabeçalho, conteúdo e rodapé no mesmo eixo |

**Teste da logo trocada:** a página sobrevive — o marca-texto sobre "Doc", a
seleção de texto em âmbar, os números em mono e o serif editorial no H1 não
aparecem num SaaS genérico.

**Decisões de design e desvios:**

1. **`next-themes` como provider de tema.** Foi instalado pelo próprio CLI do
   shadcn (o componente `sonner` importa `useTheme`). Removê-lo exigiria editar
   componente gerado e reimplementar persistência + `prefers-color-scheme`.
   **Não é biblioteca de estado global** (o escopo travado proíbe isso): é um
   provider de uma preferência de apresentação. O script inline do `index.html`
   usa a mesma chave (`talkdoc:theme`), então os dois concordam e não há piscada.
2. **Token `--text-wordmark` fora da escala de quatro degraus.** Exceção
   declarada e comentada no CSS: lockup de marca não é conteúdo, e amarrá-lo à
   escala faria a marca encolher junto com o corpo do texto. Os quatro degraus
   (`display`, `title`, `body`, `caption`) continuam valendo para todo conteúdo.
3. **Preset `nova` do CLI, não o estilo "default".** O CLI atual (shadcn 4.18)
   não aceita mais `--base-color`; a escolha de preset foi `nova` com base
   `radix`, e **todas** as cores geradas por ele foram substituídas pelos tokens
   do projeto. Nenhuma cor do preset sobreviveu.
4. **Conteúdo da home é casca, não tela.** O hero e o "como funciona" são
   texto de produto; nenhum controle de upload foi criado, conforme o escopo
   travado. A `B.3` substitui o miolo.

Nenhum outro desvio da spec ou das rules.

## 5. Comandos rodados + saídas reais

```text
# type-check (frontend)
$ cd frontend && npx tsc --noEmit
tsc exit=0

# lint (frontend)
$ cd frontend && npm run lint
> talkdoc-frontend@0.1.0 lint
> eslint src
lint exit=0

# build de produção
$ cd frontend && npm run build
dist/assets/index-BINdJNcI.css   46.18 kB │ gzip:  8.85 kB
dist/assets/index-D_x_yjhO.js   293.26 kB │ gzip: 93.76 kB
✓ built in 3.20s

# container (imagem real do Dockerfile, servida por nginx)
$ docker build -t talkdoc-frontend:b1 ./frontend   # exit 0
$ docker run -d --name talkdoc-b1 --add-host backend:127.0.0.1 -p 5173:80 talkdoc-frontend:b1
$ curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:5173/
HTTP 200

# auditoria de tema, contraste, responsividade e teclado (Playwright, contra o container)
$ python3 audit_shell.py http://localhost:5173
{
 "desktop-claro":  {"pares": 8, "reprovados": 0, "pior": 7.17},
 "desktop-escuro": {"pares": 8, "reprovados": 0, "pior": 7.15},
 "mobile-claro":   {"pares": 8, "reprovados": 0, "pior": 7.17},
 "mobile-escuro":  {"pares": 8, "reprovados": 0, "pior": 7.15},
 "desktop-toggle-aplicou-dark": true,
 "mobile-toggle-aplicou-dark": true,
 "desktop-overflow-x": 0,
 "mobile-overflow-x": 0
}

# percurso de teclado (Tab a partir do topo)
[
  {"tag": "a",      "label": "Pular para o conteúdo",     "outline": "auto 1px oklab(0.58 0.075 0.141 / 0.5)"},
  {"tag": "button", "label": "Mudar para o tema escuro",  "border": "oklch(0.58 0.16 62)"}
]

# grep de segredo/caminho local no diff (esperado: 0)
$ git diff 26ba586..HEAD -- frontend | grep -icE "GEMINI_API_KEY|/home/gabriel|DATABASE_URL"
0
```

> `make check` **não** foi rodado inteiro: seus alvos de backend
> (`ruff`, `mypy`, `lint-imports`, `pytest`) operam sobre `backend/app/`, que
> nesta branch ainda é o esqueleto vazio da `A.1` — `pytest` retorna exit 5 (sem
> testes coletados) por ausência do Track A, não por esta fase. Os gates que se
> aplicam ao Track B (`tsc --noEmit`, `eslint`) foram rodados e retornaram zero.
> Marcado `[—]` com justificativa conforme SPEC §3.10.

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-23** (design system, dois temas, 375 px, teclado, rótulo acessível) —
  toda cor vem de token semântico (nenhum hex ou cor Tailwind crua em
  componente); alternância de tema verificada pelo **botão da interface**, com
  `documentElement.classList.contains('dark') === true` após o clique nos dois
  viewports; `scrollWidth - clientWidth === 0` a 375 px; `Tab` alcança os dois
  controles (skip link e alternador), ambos com indicador de foco em traço
  âmbar; o alternador tem `aria-label` que muda com o estado.
- [x] **Contraste AA** (NFR-12) — 8 pares texto/fundo medidos por viewport e por
  tema, **zero reprovados**, pior margem 7,15:1 contra os 4,5:1 exigidos.
  Medição feita pintando a cor computada num canvas 1×1 e lendo o pixel, porque
  `getComputedStyle` devolve `oklch()` literal.
- [x] **Critério de conclusão da fase** — o container serve a casca nos dois
  temas, responsiva a 375 px, com foco visível e navegação por teclado; lint e
  typecheck zero.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (a fase define `tsc`/`lint` zero + verificação no container — todos passaram)
- [x] Comandos de validação aplicáveis limpos; gates de backend `[—]` justificados acima
- [x] Escopo travado respeitado: nenhuma biblioteca de estado global, nenhum UI kit além do shadcn, nenhuma cor fora dos tokens, `strict` do TypeScript intocado, nenhuma tela de upload ou chat criada
- [x] Nenhum segredo/PII em log, DTO ou exceção (grep zero)
- [x] Commits em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **`next-themes` entrou como dependência.** Chegou pelo componente `sonner`
   do shadcn. A leitura de que ele não é "biblioteca de estado global" no
   sentido do escopo travado merece um olhar externo. Se o avaliador discordar,
   o conserto é editar `src/components/ui/sonner.tsx` e trocar o provider por um
   `ThemeContext` de ~30 linhas.
2. **`--text-wordmark` é o quinto tamanho tipográfico do arquivo**, ainda que
   fora da escala de conteúdo e documentado como exceção. Se o avaliador ler a
   regra "no máximo quatro tamanhos" como absoluta, a marca volta para
   `text-title` e perde presença no cabeçalho.
3. **A verificação visual foi automatizada, não humana.** Contraste, tema,
   overflow e ordem de foco foram medidos por script; o julgamento estético de
   "não parece feito por IA" é meu, e a spec diz que o owner revisa e ajusta.
   Os screenshots ficaram fora do repositório (scratchpad da sessão).
4. **O gate do `make check` completo só pode rodar quando a `A.1` existir na
   mesma árvore.** Nesta branch de track, os alvos de backend não têm o que
   validar.
