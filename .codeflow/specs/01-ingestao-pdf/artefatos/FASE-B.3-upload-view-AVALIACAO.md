---
spec: 01-ingestao-pdf
fase: B.3
slug_fase: upload-view
tentativa: 1
veredito: REPROVADO
score: 8.8
threshold: 8.5
range_avaliado: cb386f4..2e43df0
---

# FASE B.3 — Avaliação independente

## 1. Veredito e score

**Veredito:** REPROVADO · **Score:** 8.8 / threshold 8.5

O score passa do threshold. **Um BLOQUEANTE reprova de qualquer forma**
(ARTIFACTS_SPEC §2.10.3): o critério de conclusão da fase — "upload de ponta a
ponta **através do `docker compose`**, não do dev server" — não foi cumprido, e
não podia ser: a `A.4`, de quem a fase declara depender, não existe em nenhuma
branch. Nesta árvore, `backend/app/` tem só os `__init__.py` do esqueleto e `db/`
está vazio.

**Isto não é uma crítica ao trabalho.** O executor detectou a violação de
elegibilidade, escreveu no topo do relatório que o protocolo mandaria parar,
executou mesmo assim por instrução direta do usuário, e marcou o critério de
conclusão como `[~] pendente` em vez de fingir que passou. Essa honestidade é a
razão de a avaliação ser rápida. Mas a constitution universal é explícita:
*"Gates duros não admitem override conversacional. Confirmação verbal não é
caminho de saída de um gate duro."* Um gate que o próprio relatório declara
pendente é um gate pendente, e `REPROVADO` é o registro correto disso.

**O que o REPROVADO significa na prática:** o código desta fase está bom e não
precisa ser reescrito. O que falta é a `A.4` existir e a fase ser revalidada
contra ela. A reavaliação depois disso deve ser barata.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 3 | **AC-20 remedido ao vivo:** arquivo de 26 MB com limite de 25 MB → toast "Arquivo grande demais / O arquivo tem 26,0 MB e o limite é 25 MB. Envie um arquivo menor…", `posts: []` (nenhuma requisição saiu) e botão de enviar `disabled: true`. **AC-21 remedido:** `Exemplo-YAITEC.pdf \| 254 KB \| Clique ou arraste outro arquivo para trocar.` **AC-23 remedido:** o input de arquivo é o 3º ponto de foco, `:focus-visible = true`, e a borda do label vira `oklch(0.58 0.16 62)` = `--ring`, com anel de 3px. Escopo travado respeitado (sem barra de progresso de upload, sem outro formato, sem cor fora dos tokens). **Nota 3 porque AC-1, AC-2 e AC-3 — os caminhos do servidor — não foram exercidos contra servidor nenhum** |
| 2 | Arquitetura e direção de dependências | 3 | 5 | Lógica pura em `hooks/useUpload.ts` (`validateSelection`, `formatFileSize` fora do componente), apresentação em `components/`, rede só via `api.ts` da `B.2`. Direção de dependência correta em todos os pontos |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `useUpload.ts:31-37` documenta que a validação local **não substitui** a do servidor — a rule `security` em uma frase, no lugar certo. Nenhum segredo (`grep` = 0). `api.ts` deixa o `Content-Type` do multipart a cargo do navegador, então não há como o `boundary` sumir |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `uploadDocument` e `ApiError` vêm da `B.2`; **nenhuma frase de erro reescrita** — a recusa passa por `notify.error(code, { message })` (`UploadDropzone.tsx:41`), com título/ação vindos do mapa. `Card`, `Button` e tokens vêm da `B.1`; zero cor própria |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Estado do envio como união discriminada (`useUpload.ts:8-11`); `SelectionProblem` carrega só o que é específico da recusa e delega o resto ao mapa |
| 6 | Local e nomes dos arquivos | 2 | 5 | Bate com a §5 (`UploadDropzone.tsx`, `useUpload.ts`, `App.tsx` alterado), + o `.test.ts` |
| 7 | Qualidade de código | 2 | 5 | `tsc` = 0, `eslint` = 0. O `<input type="file">` dentro do `<label>` é a solução correta, não gambiarra: `:has(input:focus-visible)` só casa descendente, e o comentário em `UploadDropzone.tsx:98-100` registra o porquê |
| 8 | Testes e cobertura | 2 | 2 | 6 testes, todos de função pura. Zero cobertura versionada do componente e do hook — ver I-1 |
| 9 | Migration safety (se aplicável) | 2 | — | Não se aplica |

Média ponderada (dimensões 1–8, peso total 20): 88/20 = 4,4 → **8,8/10**.

## 3. Achados BLOQUEANTES

### B-1 — Critério de conclusão da fase não cumprido: não houve upload através do backend real

**Onde:** `.codeflow/specs/01-ingestao-pdf/SPEC_01_INGESTAO_PDF.md:472` (critério
de conclusão da `B.3`) × `FASE-B.3-upload-view-EXECUCAO.md:148-150`.

A fase declara `Depende de: B.2, A.4`. Estado real da `A.4` nesta branch:

```
$ find backend/app -name "*.py" -not -path "*/.venv/*"
backend/app/__init__.py
backend/app/api/__init__.py
backend/app/core/__init__.py
backend/app/adapters/__init__.py
$ ls db/
.gitkeep
```

Não existe rota, não existe schema, não existe `EXECUCAO` de `A.1` a `A.4` em
`.codeflow/specs/01-ingestao-pdf/artefatos/`. Pela máquina de estados
(ARTIFACTS_SPEC §2.11.3) a `A.4` está **pendente**, e §2.11.4 é categórica:
uma fase só é elegível quando **todas** as fases dos seus `Depende de` estão
**concluídas**.

A verificação foi feita contra o nginx do container real apontando para um
**stub escrito à mão, não commitado**. Confirmei que o stub ainda está no ar
(`curl http://localhost:5173/api/config` → `{"max_upload_mb": 25, ...}`) — ou
seja, o que o container serve hoje é uma resposta que o executor escreveu, não
uma resposta que a `A.4` produz. Consequências concretas:

- **AC-1** (`202` com `{id, status:"pending"}` em menos de 2 s): não exercido
  contra o servidor real.
- **AC-2** (30 MB **através do nginx** → `413` com JSON `{code:"arquivo_grande"}`
  e **não HTML do nginx**): não exercido. Este é o AC que o `client_max_body_size
  30m` de §4.1 existe para atender, e é justamente o que um stub não prova —
  o executor registra isso na §9.2 do relatório.
- **AC-3** (`.txt` renomeado → `422` com `code:"arquivo_invalido"`): não
  exercido; é caminho de servidor por construção (ver §8).
- **Nomes de campo da §4.5** (`id`, `status`) não confrontados com o backend.

**Correção:** não há código a mudar aqui. Executar `A.1` → `A.4`, subir
`docker compose up --build`, repetir o ciclo de upload contra o backend real e
reavaliar. Se algum nome de campo divergir, a spec §4.5 é fonte única e quem
muda é o backend (risco 7 da spec).

## 4. Achados IMPORTANTES

### I-1 — Nenhum teste versionado cobre o comportamento do componente nem do hook

**Onde:** `frontend/src/components/UploadDropzone.tsx` (156 linhas) e
`frontend/src/hooks/useUpload.ts:64-85` — nenhum dos dois tem teste.
`useUpload.test.ts` cobre só `validateSelection` e `formatFileSize`.

O que fica sem rede de proteção: a seleção por `input` e por `drop`, a limpeza
de `inputRef.current.value` após uma recusa (`UploadDropzone.tsx:43-45`), o
estado `sending` desabilitando input e botão, o `notify.error` com a mensagem
específica, e o `onAccepted` só disparando quando `send` devolve algo. A rule
`testing` do framework é direta: *"Todo código novo deve ter teste
correspondente. Sem teste, o código não está pronto."*

A evidência de AC-20/AC-21/AC-23 existe — o executor mediu por Playwright, e
**eu remedi e confirmei tudo** —, mas nos dois casos o script vive fora do
repositório. Nada impede que o próximo diff quebre a recusa antes da requisição
sem um único gate reclamar; o executor levanta isso na §9.3 do próprio relatório.

**Correção sugerida:** `@testing-library/react` + `jsdom` no vitest, com três
testes: (a) arquivo acima do limite não chama `uploadDocument`; (b) arquivo
válido renderiza nome e tamanho; (c) durante o envio, input e botão ficam
desabilitados. É meia hora de trabalho e fecha AC-20 e AC-21 dentro do gate.

## 5. Sugestões

1. **`UploadDropzone.tsx:81-88` — `onDragLeave` no wrapper dispara ao entrar num
   filho.** `dragleave` borbulha; passar o cursor do `div` para o `label` interno
   apaga o estado "arrastando sobre" por um frame. Na prática o `onDragOver`
   contínuo o reacende, então quase não se vê — mas um contador de
   `dragenter`/`dragleave`, ou checar
   `event.currentTarget.contains(event.relatedTarget)`, elimina o tremor.
2. **`UploadDropzone.tsx:55-62` — o `drop` não respeita `limits` degradado de
   forma diferente do clique, e nem precisa.** Está correto; registro só para
   dizer que verifiquei os dois caminhos.
3. **`useUpload.ts:39` — a checagem de "é PDF" é extensão-ou-MIME, e é o certo.**
   Ver §8: a redação do relatório sobre isto é que está imprecisa, não o código.
4. **Sem botão "trocar arquivo" separado** (decisão 2 do relatório): concordo.
   Dois pontos de foco fazendo a mesma coisa é pior para teclado do que um.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 2e43df0 HEAD
2e43df0 ancestor OK

$ git diff --stat cb386f4..2e43df0 -- . ':(exclude).codeflow/specs/*/artefatos/*'
 frontend/src/App.tsx                       | 127 ++++++++++++++---------
 frontend/src/components/UploadDropzone.tsx | 156 +++++++++++++++++++++++++++++
 frontend/src/hooks/useUpload.test.ts       |  56 +++++++++++
 frontend/src/hooks/useUpload.ts            |  86 ++++++++++++++++
 4 files changed, 375 insertions(+), 50 deletions(-)

$ cd frontend && npx tsc --noEmit     # exit 0
$ npm run lint                        # exit 0
$ npm run test
 Test Files  4 passed (4)
      Tests  20 passed (20)

# estado real da A.4 — a dependência declarada da fase
$ find backend/app -name "*.py" -not -path "*/.venv/*"
backend/app/__init__.py
backend/app/api/__init__.py
backend/app/core/__init__.py
backend/app/adapters/__init__.py
$ ls db/
.gitkeep
$ ls .codeflow/specs/01-ingestao-pdf/artefatos/ | grep '^FASE-A'
(vazio)

# AC-20 e AC-21 — remedidos pelo avaliador, com Playwright, contra o container
$ python3 audit2.py http://localhost:5173
 "ac20": {
   "toast": ["Arquivo grande demais | O arquivo tem 26,0 MB e o limite é 25 MB.
              Envie um arquivo menor ou divida o documento em partes."],
   "posts": [],                       <- nenhuma requisição saiu
   "botao_desabilitado": [true]
 }
 "ac21": "Exemplo-YAITEC.pdf | 254 KB | Clique ou arraste outro arquivo para trocar."

# AC-23 (teclado) — 3º ponto de foco
 { "tag": "input", "type": "file",
   "nome": "Exemplo-YAITEC.pdf | 254 KB | Clique ou arraste outro arquivo para tro",
   "focusVisible": true,
   "caixaFoco": { "borderColor": "oklch(0.58 0.16 62)",
                  "boxShadow": "oklab(0.58 0.075 0.141 / 0.5) 0px 0px 0px 3px" } }

# .txt renomeado para .pdf (nome .pdf, conteúdo texto) — o cliente NÃO bloqueia
 "txt_renomeado": { "toasts": [],
                    "label": "disfarcado.pdf | 17 B | Clique ou arraste outro arquivo para trocar." }

# escopo travado
$ grep -rniE "GEMINI_API_KEY|DATABASE_URL|/home/gabriel|api[_-]?key" src
(vazio)
$ grep -rnE "XMLHttpRequest|onUploadProgress|upload\.onprogress" src
(vazio)   <- nenhuma barra de progresso de upload prometida

$ git status --short
(vazio — árvore limpa ao final)
```

## 7. Itens da fase / DoD não atendidos

- **Critério de conclusão da fase** — "upload de ponta a ponta através do
  `docker compose`". Não cumprido (B-1). O executor já o marcava `[~]`.
- **AC-1, AC-2, AC-3** — não exercidos contra servidor real (B-1).
- **Elegibilidade (§2.11.4)** — a fase rodou com `A.4` **pendente**. Diferente da
  `B.2`, esta não se resolve com uma aprovação: exige que o Track A avance.
- **Testes do componente e do hook** — I-1.
- **Gates de backend do `make check`** — `[—]` justificado e confirmado
  (`make check` falha em `arch`: `Could not find .importlinter`, arquivo da
  `A.1`). Correto (SPEC §3.10).

## 8. Divergências entre o relatório e o código real

### D-1 — "`.txt` renomeado é bloqueado no cliente" não é o que o código faz

`FASE-B.3-upload-view-EXECUCAO.md:145-147` afirma:

> **Recusa de formato** — `.txt` renomeado é bloqueado no cliente, sem
> requisição.

`useUpload.ts:39` decide assim:

```ts
const looksLikePdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
```

É um **OU**: um arquivo chamado `disfarcado.pdf` com conteúdo de texto passa pela
extensão, qualquer que seja o MIME. Verifiquei ao vivo — selecionei
`{name: "disfarcado.pdf", mimeType: "text/plain"}` e a interface **aceitou**:
zero toast, e o label passou a mostrar `disfarcado.pdf | 17 B`. O que o teste
`useUpload.test.ts:33-37` cobre é um `planilha.xlsx`, que é outro caso — nome e
MIME ambos não-PDF.

**O código está certo; a frase do relatório é que está errada.** A spec atribui a
detecção de conteúdo ao servidor (AC-3: assinatura `%PDF` → `422`), e é
tecnicamente impossível fazê-la só pela extensão. O que o cliente faz —
peneirar o óbvio e deixar a palavra final com o servidor — é exatamente o que o
escopo travado da fase manda ("validação no cliente **não** substitui a do
servidor"). Corrigir a redação para "arquivo sem extensão nem MIME de PDF é
bloqueado no cliente; conteúdo disfarçado é responsabilidade do `422` da `A.4`".

### D-2 — "o botão 'Enviar documento' é o quarto ponto de foco"

Verdadeiro **depois** de escolher um arquivo (medi: 4 pontos). Na tela vazia o
botão está `disabled` e sai da ordem de foco, restando 3. A afirmação da §6 do
relatório não diz de qual estado fala. Detalhe de redação, sem impacto.

Fora isso, tudo o que o relatório afirma se confirmou: `ac20_nenhum_post`,
o tamanho real na mensagem, o nome e o tamanho na área, e o `--ring` na borda do
label sob foco de teclado.
