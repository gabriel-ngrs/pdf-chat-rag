---
spec: 01-ingestao-pdf
fase: B.4
slug_fase: processing-status
tentativa: 1
veredito: REPROVADO
score: 8.6
threshold: 8.5
range_avaliado: f00210e..e93a748
---

# FASE B.4 — Avaliação independente

## 1. Veredito e score

**Veredito:** REPROVADO · **Score:** 8.6 / threshold 8.5

Um BLOQUEANTE, que reprova qualquer que seja o score (ARTIFACTS_SPEC §2.10.3):
o critério de conclusão da fase — "ciclo `upload → processando → pronto`
observável **no compose**" — foi cumprido contra um stub não commitado, e a
`B.3`, de quem esta fase depende, está **reprovada** pelo mesmo motivo. A
cadeia inteira aguarda a `A.4`.

O que precisa ser dito com clareza: **rodei o ciclo completo eu mesmo, no
navegador, contra o container**, e tudo o que o relatório afirma se confirmou —
inclusive as duas coisas mais fáceis de fingir num relatório, a janela de
progresso legitimamente indeterminado e a parada do polling em estado terminal.
A qualidade do que foi entregue não é o problema. O problema é contra o que foi
verificado.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 3 | **Ciclo remedido ao vivo:** `Na fila → Lendo o documento → Pronto` numa única sessão de página, sem reload (AC-22). `aria-valuenow` `"33"` → `"67"`, monotônico (AC-12), com `aria-valuetext: "4 de 12 trechos"`. Houve janela indeterminada real (skeleton, `valuenow: null`) enquanto `chunks_total` era nulo. Polling: menor intervalo medido **1,5 s** (piso da spec é 1 s), 5 requisições até `Pronto` e **5 depois de 5 s adicionais** — parou. `localStorage` guardou o id e o F5 voltou em `Pronto`. `role="status"` presente. **Nota 3 porque tudo isso foi contra o stub, não contra a `A.4`** |
| 2 | Arquitetura e direção de dependências | 3 | 5 | Efeito e timer isolados em `hooks/useDocumentStatus.ts`; `progressPercent` é função pura exportada e testável; `ProcessingStatus.tsx` só apresenta. Rede só via `api.ts` da `B.2` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | A mensagem de falha exibida é a `error_message` do backend (`ProcessingStatus.tsx:103-106`), com fallback próprio quando nula; nenhuma stack trace, nenhum corpo bruto, nenhum `code` cru na tela. `grep` de segredo = 0 |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `fetchDocument`/`ApiError` da `B.2`; `describeError('nao_encontrado')` reusado em vez de reescrever a frase de 404 (`ProcessingStatus.tsx:60`); `Card`, `Progress`, `Skeleton`, `Badge`, `Button` da `B.1`; zero cor nova |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Os quatro estados de FR-9 num `Record` tipado (`ProcessingStatus.tsx:20-37`); separação explícita entre falha terminal (`nao_encontrado`) e transitória (`useDocumentStatus.ts:79-85`), com o porquê no comentário |
| 6 | Local e nomes dos arquivos | 2 | 5 | Bate com a §5; `UploadDropzone.tsx` **não** foi alterado e a razão está declarada no relatório ("o `App` é quem alterna") — menos diff é o que a constitution universal pede |
| 7 | Qualidade de código | 2 | 4 | `tsc` = 0, `eslint` = 0. Cadeia de `setTimeout` em vez de `setInterval`, com o porquê registrado; cleanup correto e verificado. Desconto por I-1: o defeito do primitivo foi contornado no chamador em vez de corrigido na fonte |
| 8 | Testes e cobertura | 2 | 2 | 4 testes, todos de `progressPercent` — e são bons (cobrem `null`, zero, arredondamento e clamp). Zero cobertura versionada do polling, que é o miolo da fase — ver I-2 |
| 9 | Migration safety (se aplicável) | 2 | — | Não se aplica |

Média ponderada (dimensões 1–8, peso total 20): 86/20 = 4,3 → **8,6/10**.

## 3. Achados BLOQUEANTES

### B-1 — Critério de conclusão não cumprido: o ciclo não foi observado no compose

**Onde:** `SPEC_01_INGESTAO_PDF.md:492` (critério de conclusão da `B.4`) ×
`FASE-B.4-processing-status-EXECUCAO.md:151-152`.

Herdado da `B.3` e da ausência da `A.4`, exatamente como o relatório declara.
Confirmei que o container em `localhost:5173` continua servindo contra o stub do
executor, não contra um backend do projeto:

```
$ curl -s http://localhost:5173/api/config
{"max_upload_mb": 25, "max_pdf_pages": 20, "max_extracted_chars": 60000}
$ find backend/app -name "*.py" -not -path "*/.venv/*"
backend/app/__init__.py … (só os __init__ do esqueleto)
```

Pela máquina de estados (§2.11.3) a `B.3` fica **reprovada** após esta rodada, e
§2.11.4 diz que dependência não-concluída não libera quem depende dela.

O risco concreto que sobra é o que o executor nomeia na §9.1 do relatório: os
nomes de campo (`chunks_processed`, `chunks_total`, `page_count`,
`error_message`) e o fato de `chunks_total` chegar `null` antes do chunking foram
validados contra um stub que o próprio executor escreveu a partir da §4.5 — o
que confirma a leitura dele da spec, não o comportamento do backend. A §4.5 é
fonte única e, se divergirem, quem muda é o backend; mas ninguém conferiu ainda.

**Correção:** executar `A.1`–`A.4`, subir `docker compose up --build`, enviar o
`Exemplo-YAITEC.pdf` e reavaliar `B.3` e `B.4` juntas.

## 4. Achados IMPORTANTES

### I-1 — `src/components/ui/progress.tsx:6-19` descarta o `value` e nunca o repassa ao primitivo

```tsx
function Progress({ className, value, ...props }) {
  return (
    <ProgressPrimitive.Root data-slot="progress" className={...} {...props}>
      <ProgressPrimitive.Indicator style={{ transform: `translateX(-${100 - (value || 0)}%)` }} />
```

`value` é desestruturado, usado só no `transform` do indicador, e **nunca chega
ao `ProgressPrimitive.Root`**. O Radix calcula os atributos ARIA a partir dele:

```js
// node_modules/@radix-ui/react-progress/dist/index.mjs:36-43
"aria-valuemax": max, "aria-valuemin": 0,
"aria-valuenow": isNumber(value) ? value : void 0,
"aria-valuetext": valueLabel,
"data-state": getProgressState(value, max),
"data-value": value ?? void 0,
```

Sem o `value`, todos caem para indeterminado. Foi isso que o executor mediu e
descreveu na decisão 5 do relatório — e o diagnóstico dele está certo. O que
não está certo é a correção escolhida: em vez da fonte (uma linha), foi um
remendo no chamador, `aria-valuenow` e `aria-valuetext` passados à mão em
`ProcessingStatus.tsx:132-133`.

Confirmei ao vivo que o remendo funciona (o `{...progressProps}` do Radix vem
por último, então o chamador vence) **e** que a causa raiz continua lá:

```
{"estado": "Lendo o documento", "valuenow": "67", "valuetext": "8 de 12 trechos",
 "ariaLabel": "Progresso da leitura do documento", "dataState": "indeterminate"}
```

`data-state: "indeterminate"` a 67%. Consequências que sobram: `data-value` e
`data-max` ausentes, qualquer estilo futuro em `data-[state=complete]:` morto em
silêncio, e todo consumidor seguinte — a começar pelo progresso de citação da
`FEAT-0002` — obrigado a repetir o remendo ou a herdar a barra muda. §4.7 da spec
é explícita: os componentes do shadcn "passam a ser **código do projeto**,
versionado e editável".

**Correção sugerida** (`frontend/src/components/ui/progress.tsx:12`):

```tsx
<ProgressPrimitive.Root data-slot="progress" value={value} className={...} {...props}>
```

Feito isso, os `aria-valuenow`/`aria-valuetext` de `ProcessingStatus.tsx` viram
redundância — o `aria-valuetext` pode ficar, porque "8 de 12 trechos" diz mais
que os "67%" que o Radix geraria sozinho.

### I-2 — Nenhum teste versionado cobre o polling, que é o miolo da fase

**Onde:** `frontend/src/hooks/useDocumentStatus.ts:49-99` e
`frontend/src/components/ProcessingStatus.tsx` (193 linhas). O único teste é
`useDocumentStatus.test.ts`, e cobre apenas `progressPercent`.

Sem teste ficam: a parada em `ready`/`failed`, a limpeza do timeout no cleanup, o
tratamento de `nao_encontrado` como terminal, a tolerância a falha de rede
mantendo o último estado, o intervalo mínimo, e a retomada por `localStorage`.
São exatamente os itens do escopo travado da fase ("não deixar timer órfão",
"não fazer polling mais agressivo que 1 s"). A rule `testing` é direta: *"Todo
código novo deve ter teste correspondente."*

Verifiquei todos eles ao vivo e passam hoje. O problema é que nada os protege
amanhã, e o executor levanta o ponto na §9.4 do próprio relatório.

**Correção sugerida:** com `vi.useFakeTimers()` e um `fetchDocument` falso, três
testes fecham o essencial sem precisar de DOM: (a) para de chamar depois de
`ready`; (b) `nao_encontrado` marca `missing` e não reagenda; (c) erro de rede
mantém `document` e reagenda. Uma quarta com `@testing-library/react` cobre a
retomada por `localStorage`.

## 5. Sugestões

1. **`ProcessingStatus.tsx:56` e `useDocumentStatus.ts:67` — a variável `document`
   sombreia o `document` global do DOM.** Funciona e o `tsc` não reclama, mas num
   arquivo que também mexe com foco e `aria` é um nome infeliz. `doc` ou
   `documentDetail` custam nada.
2. **`ProcessingStatus.tsx:142-156` — dois blocos quase idênticos** para o botão
   "Enviar outro documento" em `failed` e em `ready`, diferindo só na `variant`.
   Um `{(failed || ready) && <Button variant={failed ? 'default' : 'outline'}>}`
   diz o mesmo em um terço das linhas.
3. **`ProcessingStatus.tsx:93` — o `role="status"` é remontado na transição do
   esqueleto para o card.** Live region recém-inserida no DOM costuma não ser
   anunciada; a primeira mudança de estado pode passar em silêncio. Manter um
   `<p role="status">` presente desde o esqueleto resolve. Da segunda transição
   em diante funciona — confirmei que o texto muda no mesmo elemento.
4. **`useDocumentStatus.ts:87` — o retry de rede não tem teto.** Com o backend
   fora, o polling continua para sempre a 1,5 s. É coerente com "falha de rede
   não derruba o estado", e para uma entrega local não incomoda; se quiser
   endurecer, um backoff depois de N falhas seguidas.
5. **1,5 s de intervalo** (§9.2 do relatório): concordo com o número e com o
   raciocínio. O NFR-1 diz que o backend atualiza no máximo a cada 15 s;
   perguntar mais rápido não revelaria nada. Nenhuma ação.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor e93a748 HEAD
e93a748 ancestor OK

$ git diff --stat f00210e..e93a748 -- . ':(exclude).codeflow/specs/*/artefatos/*'
 frontend/src/App.tsx                         |  13 +-
 frontend/src/components/ProcessingStatus.tsx | 193 +++++++++++++++++++++++++++
 frontend/src/hooks/useDocumentStatus.test.ts |  38 ++++++
 frontend/src/hooks/useDocumentStatus.ts      | 102 ++++++++++++++
 4 files changed, 340 insertions(+), 6 deletions(-)

$ cd frontend && npx tsc --noEmit     # exit 0
$ npm run lint                        # exit 0
$ npm run test
 Test Files  4 passed (4)
      Tests  20 passed (20)

# ciclo completo remedido pelo avaliador, com Playwright, contra o container
$ python3 b4.py
{
 "amostras": [
  {"estado": "Na fila",           "valuenow": null, "skeleton": true,  "dataState": null},
  {"estado": "Lendo o documento", "valuenow": null, "skeleton": true,  "dataState": null},
  {"estado": "Lendo o documento", "valuenow": "33", "skeleton": false, "dataState": "indeterminate",
   "valuetext": "4 de 12 trechos", "ariaLabel": "Progresso da leitura do documento"},
  {"estado": "Lendo o documento", "valuenow": "67", "skeleton": false, "dataState": "indeterminate",
   "valuetext": "8 de 12 trechos"},
  {"estado": "Pronto",            "valuenow": null, "skeleton": false, "dataState": null}
 ],
 "n_polls": 5,
 "polls_depois_5s": 5,            <- polling parou em estado terminal
 "menor_intervalo_s": 1.5,        <- piso da spec é 1 s
 "id_persistido": "3b091fda-c859-4945-8b60-e31f99fca1ee",
 "apos_f5": "Pronto"              <- retomada por localStorage
}

# causa raiz do aria-valuenow ausente (I-1)
$ sed -n '36,43p' node_modules/@radix-ui/react-progress/dist/index.mjs
        "aria-valuemax": max,
        "aria-valuemin": 0,
        "aria-valuenow": isNumber(value) ? value : void 0,
        "aria-valuetext": valueLabel,
        role: "progressbar",
        "data-state": getProgressState(value, max),
        "data-value": value ?? void 0,
        "data-max": max,
        ...progressProps,

# estado real da A.4
$ curl -s http://localhost:5173/api/config
{"max_upload_mb": 25, "max_pdf_pages": 20, "max_extracted_chars": 60000}   <- stub, não A.4
$ ls .codeflow/specs/01-ingestao-pdf/artefatos/ | grep '^FASE-A'
(vazio)

$ grep -riE "GEMINI_API_KEY|DATABASE_URL|/home/gabriel|api[_-]?key" src
(vazio)

$ git status --short
(vazio — árvore limpa ao final)
```

## 7. Itens da fase / DoD não atendidos

- **Critério de conclusão da fase** — ciclo observável no compose. Não cumprido
  (B-1); o executor já o marcava `[~]`.
- **Elegibilidade (§2.11.4)** — a fase rodou com a `B.3` em "aguardando
  avaliação" e a `A.4` **pendente**. Só se resolve com o Track A.
- **Teste do polling e do componente** — I-2.
- **`aria-valuenow` na origem** — I-1: o atributo aparece na tela, mas o
  primitivo do projeto continua quebrado.
- **Gates de backend do `make check`** — `[—]` justificado e confirmado
  (`make check` falha em `arch`: `Could not find .importlinter`, arquivo da
  `A.1`). Correto (SPEC §3.10).
- **`make check` sem os testes do frontend** — herdado do I-1 da `B.2`.

## 8. Divergências entre o relatório e o código real

Nenhuma divergência de fato. Confrontei cada afirmação da §6 do relatório com
medição própria e todas se sustentam: transição sem reload, `[33, 67]`
monotônico, janela indeterminada real, `role="status"`, F5 retomando,
`polling_parou_em_pronto`, intervalo de 1,5 s. Os números que medi batem com os
do relatório.

Duas notas de leitura, não de divergência:

1. **A decisão 5 do relatório** ("o primitivo desenhava a barra sem expor
   `aria-valuenow`") descreve corretamente o sintoma, mas não diz que a causa
   está num arquivo do próprio projeto e continua lá — o que o leitor do
   relatório tende a concluir é que o assunto foi resolvido. Ver I-1.
2. **`reset_limpou_storage: null`** na saída do relatório é o valor lido de
   `localStorage` depois do reset (isto é: limpou), não uma verificação que
   falhou. A chave de saída é ambígua; renomear para
   `documento_em_storage_apos_reset` diria o que quer dizer.
