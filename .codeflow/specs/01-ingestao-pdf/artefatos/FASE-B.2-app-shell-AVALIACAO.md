---
spec: 01-ingestao-pdf
fase: B.2
slug_fase: app-shell
tentativa: 1
veredito: RESSALVAS
score: 9.3
threshold: 8.5
range_avaliado: f01ed27..fcc36eb
---

# FASE B.2 — Avaliação independente

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 9.3 / threshold 8.5

Zero BLOQUEANTES. Um IMPORTANTE: a fase introduziu 10 testes e um runner novo, e
**nenhum gate do projeto os executa** — `make check` continua rodando só o
`pytest` do backend. O código em si é o melhor pedaço do track: o envelope da
§4.3 é respeitado à risca, o fallback de resposta não-JSON existe nos dois
caminhos, e não há um único número de limite duplicado no cliente.

Ressalva de processo, sem efeito no veredito: a fase foi executada quando a `B.1`
estava em **aguardando avaliação**, não **concluída** — ARTIFACTS_SPEC §2.11.4
diz que dependência apenas aguardando avaliação não libera quem depende dela.
Como a `B.1` recebeu `APROVADO` nesta mesma rodada, a pré-condição está
satisfeita agora e não há retrabalho de código a fazer por causa disso. Registro
para o histórico, não como achado.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | **Mapeia por `code`, nunca por status:** `grep -rnE "\.status ===? *[0-9]{3}"` em `src/` = 0; `describeError(code: string)` (`errors.ts:83`) não recebe status, e `ApiError.status` está documentado como diagnóstico (`api.ts:11-13`). **Sem limite duplicado:** `config.ts:20-21` declara a ausência de fallback e `maxUploadBytes` deriva de `limits`. **Sem `alert()`, sem stack trace:** `grep` de `alert(`/`console.` = 0; `describeError` devolve frase própria, nunca `error.message` do servidor bruto. Os 5 códigos de §4.3 + `rede_indisponivel` estão em `ERROR_CODES` (`errors.ts:23-30`) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `lib/` (dados), `hooks/`, `components/` como a constitution do projeto exige. `api.ts` é o **único** ponto de `fetch` do app (`grep -rn "fetch(" src` só casa `api.ts:60`); `config.ts` depende de `api.ts`, nunca o contrário |
| 3 | Segurança / LGPD / multi-tenant | 3 | 4 | Nenhum segredo (`grep` = 0). `session.ts:20-22` documenta explicitamente que o `X-Session-Id` **não é fronteira de segurança**, alinhado à §4.5 — é a coisa certa a escrever num arquivo que gera um id. Todo request tem `AbortController` com timeout (`api.ts:55-56`). Desconto pequeno: o `clearTimeout` no `finally` (`api.ts:71-73`) desarma o timeout **antes** da leitura do corpo, então um corpo que nunca termina de chegar não é cortado por ninguém |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `Notices.tsx` é uma casca de 28 linhas sobre o `sonner` da `B.1`; nenhum componente de aviso escrito do zero; nenhuma cor própria — só `text-muted-foreground` e os tokens `--popover`/`--border` que o primitivo já lê |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `types.ts` espelha a §4.5 campo a campo em snake_case, com o porquê registrado (`types.ts:6-7`): renomear criaria camada de tradução que esconde divergência. É exatamente o que o risco 7 da spec pede |
| 6 | Local e nomes dos arquivos | 2 | 5 | Bate com "Arquivos novos" da §5 (+ os dois `.test.ts`, adição coerente com a subseção "Testes" da fase) |
| 7 | Qualidade de código | 2 | 5 | `tsc --noEmit` = 0, `eslint src` = 0. Funções curtas, sem duplicação; `readErrorEnvelope` (`api.ts:33-48`) valida o shape antes de confiar, em vez de fazer cast cego |
| 8 | Testes e cobertura | 2 | 3 | 10 testes, e são bons: cobrem sucesso, envelope de erro, HTML no caminho de erro **e** no de sucesso, falha de rede e o fallback de código desconhecido. Desconto pelo IMPORTANTE abaixo — teste que nenhum gate roda não protege ninguém de regressão |
| 9 | Migration safety (se aplicável) | 2 | — | Não se aplica |

Média ponderada (dimensões 1–8, peso total 20): 93/20 = 4,65 → **9,3/10**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

### I-1 — `Makefile:29-30` — os testes do frontend ficaram fora de todo gate

```make
test:
	cd backend && uv run pytest
```

A fase acrescentou `vitest` e o script `npm run test` (`frontend/package.json:10`)
e escreveu 10 testes. O alvo `test:` do `Makefile` não os chama, e `check:` é
`lint typecheck arch test`. Resultado: **`make check` pode ficar verde com os 10
testes vermelhos**. A DoD global da spec (§9) diz "`make check` (lint +
typecheck + arch + test) retorna zero" — hoje esse "test" cobre metade do
projeto.

O executor reportou o item honestamente (§9.1 do relatório) e **se recusou a
editar o `Makefile` por ser arquivo fora da lista da fase e compartilhado com o
Track A**. A recusa é o comportamento correto pela constitution universal
(falha de Escopo → parar e reportar). O que não é aceitável é a fase fechar com
o buraco aberto.

**Correção sugerida** (uma linha; o risco de conflito que motivou a recusa não
existe mais — `dev` já tem os dois tracks na mesma árvore):

```make
test:
	cd backend && uv run pytest
	cd frontend && npm run test
```

Verifiquei que funciona: `cd frontend && npm run test` → `Test Files 4 passed
(4) / Tests 20 passed (20)`, sem rede e sem banco, compatível com o NFR-4.

## 5. Sugestões

1. **`errors.ts:19` — o campo `severity` nasceu morto.** `ErrorDescription`
   carrega `severity`, todas as seis entradas valem `'error'`, e
   `notify.error()` (`useNotices.ts:34-40`) nunca o lê — chama `toast.error`
   direto. O teste até afirma `expect(description.severity).toBe('error')`
   (`errors.test.ts:27`), o que cristaliza o campo sem lhe dar uso. Ou o
   `notify` passa a despachar por `severity`, ou o campo sai.
2. **`useNotices.ts:47-49` — `useNotices()` não é um hook.** Devolve um objeto de
   módulo constante, sem estado nem efeito. Funciona e é estável nas listas de
   dependência (`App.tsx:59`), mas o nome promete uma indireção que não existe;
   importar `notify` direto diria a mesma coisa com menos cerimônia. Se a
   intenção era abrir espaço para um provider depois, vale uma linha de
   comentário dizendo isso.
3. **`api.ts:71-73` — o timeout não cobre a leitura do corpo.** `clearTimeout`
   no `finally` do `fetch` desarma o `AbortController` antes do
   `await response.json()`. Um servidor que responde os headers e trava no corpo
   pendura a promessa para sempre. Mover o `clearTimeout` para depois da leitura
   (ou usar `finally` no `request` inteiro) fecha o caso.
4. **Timeout de upload de 120 s (`api.ts:7`)** — o executor pergunta na §9.3 do
   relatório se deveria virar variável. Minha leitura: não. É constante de
   cliente, não limite de negócio, e o comentário já diz o porquê do número. Os
   limites que precisam de fonte única (`max_upload_mb` e companhia) já vêm da
   API, que é o que importava.
5. **`api.ts` com os três endpoints numa fase só** (§9.2 do relatório) —
   concordo com a decisão do executor. A alternativa era tocar, em `B.3` e `B.4`,
   um arquivo que aquelas fases não declaram. O que ele fez produz **menos**
   violação de escopo, não mais. Nenhuma ação.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor fcc36eb HEAD
fcc36eb ancestor OK

$ git diff --stat f01ed27..fcc36eb -- . ':(exclude).codeflow/specs/*/artefatos/*'
 frontend/package-lock.json          | 364 +++++++++++++++++++++++++++++++++++-
 frontend/package.json               |   6 +-
 frontend/src/App.tsx                |  64 ++++++-
 frontend/src/components/Notices.tsx |  28 +++
 frontend/src/hooks/useNotices.ts    |  49 +++++
 frontend/src/lib/api.test.ts        | 102 ++++++++++
 frontend/src/lib/api.ts             | 108 +++++++++++
 frontend/src/lib/config.ts          |  34 ++++
 frontend/src/lib/errors.test.ts     |  39 ++++
 frontend/src/lib/errors.ts          |  85 +++++++++
 frontend/src/lib/session.ts         |  32 ++++
 frontend/src/lib/types.ts           |  43 +++++
 12 files changed, 945 insertions(+), 9 deletions(-)

$ cd frontend && npm run test
 RUN  v4.1.10
 Test Files  4 passed (4)
      Tests  20 passed (20)
   Duration  298ms

$ npx tsc --noEmit          # exit 0
$ npm run lint              # eslint src, exit 0
$ npm audit --audit-level=high
found 0 vulnerabilities

# escopo travado — mapeamento por status HTTP
$ grep -rnE "\.status ===? *[0-9]{3}|status *[=!]== *[0-9]{3}" src --include=*.ts --include=*.tsx
(vazio)

# escopo travado — alert() / stack trace / console
$ grep -rnE "\balert\(|console\.(log|error|warn)" src --include=*.ts --include=*.tsx | grep -v /ui/
(vazio)

# escopo travado — único ponto de fetch
$ grep -rn "fetch(" src --include=*.ts --include=*.tsx
src/lib/api.ts:60:    response = await fetch(`${BASE_URL}${path}`, {

$ grep -riE "GEMINI_API_KEY|DATABASE_URL|/home/gabriel|api[_-]?key" src
(vazio)

# gate da fase, contra o container real (nginx do Dockerfile) em pé
$ curl -s -o /dev/null -w "app HTTP %{http_code}\n" http://localhost:5173/
app HTTP 200
$ curl -s http://localhost:5173/api/config
{"max_upload_mb": 25, "max_pdf_pages": 20, "max_extracted_chars": 60000}

# aviso de erro com título + mensagem + ação, remedido pelo avaliador na B.3
[{"title": "Arquivo grande demais",
  "description": "O arquivo tem 26,0 MB e o limite é 25 MB. Envie um arquivo menor ou divida o documento em partes."}]

$ git status --short
(vazio — árvore limpa ao final)
```

## 7. Itens da fase / DoD não atendidos

- **I-1** — os testes do frontend fora do `make check`. Único item de retrabalho.
- **Gates de backend do `make check`** — `[—]` justificado e confirmado por mim
  (`make check` falha em `arch`: `Could not find .importlinter`, arquivo da
  `A.1`). Correto marcar `[—]` (SPEC §3.10).
- **Elegibilidade (§2.11.4)** — a fase rodou com a `B.1` em "aguardando
  avaliação". Sanado pelo `APROVADO` da `B.1` nesta rodada; sem retrabalho.
- **`package.json`/`package-lock.json` fora da lista de arquivos da fase** — o
  executor declarou o desvio na §4 do relatório e a razão é sólida (a subseção
  "Testes" da fase exige testes e não havia runner). Aceito.

## 8. Divergências entre o relatório e o código real

Nenhuma. Os quatro critérios de aceite declarados na §6 do relatório se
sustentam contra o código e contra os testes que rodei:

- "os cinco códigos da spec estão em `ERROR_CODES`, cada um com
  título/mensagem/ação não vazios, nenhum título repetido, desconhecido cai em
  `erro_interno`" → `errors.test.ts:14-38` faz exatamente essas quatro
  asserções, e passam. **Confirma.**
- "fallback de não-JSON em dois pontos, não um" → `api.ts:33-48` (erro) e
  `api.ts:80-84` (sucesso), com um teste para cada. **Confirma.**
- "`ApiError` guarda o `status`, mas nenhuma decisão de mensagem o consulta" →
  `grep` de comparação por status = 0. **Confirma.**
- "sem constante de limite no cliente" → `config.ts` não tem nenhum número.
  **Confirma.**
