---
spec: 01-ingestao-pdf
fase: B.2
slug_fase: app-shell
tentativa: 2
veredito: APROVADO
score: 9.6
threshold: 8.5
range_avaliado: f01ed27..3be5eed
---

# FASE B.2 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.6 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. O único achado da tentativa 1 — os testes do
frontend fora de todo gate — está fechado, e **eu provei que o gate agora morde**,
não só que ele existe. As três sugestões acatadas foram bem executadas: a
`severity` do mapa deixou de ser decoração e passou a escolher o canal, e o
timeout do `api.ts` passou a cobrir a leitura do corpo com a reclassificação
correta (corte de timeout é falta de resposta, não resposta estranha).

**Nota sobre o range.** O `range` declarado (`f01ed27..3be5eed`) engloba, além
do rework, todo o Track A mergeado no meio do caminho. Auditei o que de fato
mudou nesta tentativa pelo intervalo real do rework, `34cb479..3be5eed`, que é o
conjunto dos cinco commits de código. Registro para quem reler não achar que o
backend inteiro entrou nesta fase.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | Escopo travado intacto após o rework: `grep -rnE "\.status ===? *[0-9]{3}"` = 0; `grep` de `alert(`/`console.` = 0; `config.ts` continua sem número de fallback. **`make check` = 0 rodado por mim**, agora com as duas suítes (119 backend + 40 frontend) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `api.ts` segue o único ponto de `fetch` (`grep -rn "fetch(" src` → uma ocorrência, `api.ts:60`); `CHANNEL_BY_SEVERITY` (`useNotices.ts:16-20`) mantém o despacho num lugar só, em vez de espalhar `toast.*` pelos componentes |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | O `clearTimeout` migrou para um `finally` que envolve o `request` inteiro (`api.ts:56-93`): resposta que trava no corpo agora é cortada. A reclassificação `controller.signal.aborted → rede_indisponivel` é a leitura certa. `grep` de segredo em `frontend/src` = 0; `make security` = 0 (bandit, pip-audit, npm audit) |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Nada reescrito; `Notices.tsx` intocado, continua casca sobre o `sonner` da `B.1` |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `types.ts` espelha a §4.5 — e o payload real do backend **confirmou** o espelhamento (ver a avaliação da `B.4`, §6: sete campos, nem um a mais nem um a menos) |
| 6 | Local e nomes dos arquivos | 2 | 5 | O rework tocou `Makefile`, `api.ts`, `useNotices.ts`, `package.json` — todos coerentes com os achados; nenhum arquivo alheio |
| 7 | Qualidade de código | 2 | 4 | Cada mudança carrega o "por quê" no comentário, e nenhum é redundante. Desconto por `semResposta` (`api.ts:57`), identificador em pt-BR num código cuja spec fixa "identificadores em inglês" — ver §5 |
| 8 | Testes e cobertura | 2 | 4 | 10 testes, agora dentro do gate. Desconto: a mudança de comportamento do timeout (corte do corpo virando `rede_indisponivel`) entrou sem teste próprio |
| 9 | Migration safety (se aplicável) | 2 | — | Não se aplica |

Média ponderada (dimensões 1–8, peso total 20): 96/20 = 4,8 → **9,6/10**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

**I-1 da tentativa 1 (testes do frontend fora de todo gate) — FECHADO.** Não
aceitei "está no Makefile" como prova; verifiquei os três elos da corrente:

1. A linha existe (`Makefile:24`) e `make check` executou de fato as duas suítes
   — 119 testes de backend com cobertura de `core/` em 98,98%, e 40 de frontend.
2. `vitest` devolve exit não-zero quando um teste falha: rodei
   `npx vitest run --root=<temp>` com um caso falhando de propósito → `exit=1`.
3. `make` aborta o alvo na primeira linha de receita que falha: alvo de teste com
   `@true` / `@false` / `@echo NUNCA_CHEGA` → `Error 1`, e `NUNCA_CHEGA` não é
   impresso.

Ou seja: uma quebra no frontend agora reprova `make check`. Era exatamente isso
que faltava.

## 5. Sugestões

1. **`api.ts:57` — `semResposta` é identificador em pt-BR.** A spec fixa em §1.1,
   item 8 ("Identificadores em inglês; textos ao usuário em pt-BR") e repete na
   DoD global. É a **única** ocorrência em código de produção do frontend
   inteiro (varredura completa) — `noResponse` fecha o assunto. Há mais 11 em
   arquivos de teste (`documento`, `campoDeArquivo`, `montar`, `titulo`,
   `opcoes`, `avancar`, `CODIGOS_DA_SPEC`…). **Não bloqueio**, por dois motivos
   que quero deixar explícitos: a spec põe esse item em "Itens globais
   transversais" da §9, não no gate por fase; e parte dessas ocorrências já
   existia na tentativa 1 e passou por mim sem ser apontada — a falha de leitura
   foi minha, e não é justo cobrá-la agora como se fosse regressão. Fica como
   item de fechamento da FEAT-0001, não desta fase.
2. **O novo caminho do timeout não tem teste.** `api.test.ts` cobre falha de
   rede no `fetch`, mas não o corte durante a leitura do corpo — que é
   justamente o que mudou. Um teste com um `ReadableStream` que nunca fecha,
   `vi.useFakeTimers()` e a asserção `code === 'rede_indisponivel'` fecha a
   regressão em ~15 linhas.
3. **`CHANNEL_BY_SEVERITY` (`useNotices.ts:16-20`) tipa `show` como
   `typeof toast.error`.** Funciona porque as três assinaturas coincidem hoje;
   se o `sonner` divergir uma delas, o erro aparece longe da causa. Um alias
   `type ToastFn = (title: string, opts?: ExternalToast) => unknown` diria a
   intenção sem depender dessa coincidência.
4. **Hoje `describeError` devolve `severity: 'error'` em todos os seis códigos**,
   então o despacho novo ainda não muda nada na prática. Está certo assim — o
   valor da mudança é o código futuro marcado como aviso não sair vermelho. Só
   registro que a tabela ainda não é exercitada por nenhum caso real.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 3be5eed HEAD
3be5eed ancestor OK

# intervalo real do rework (o range declarado engloba o Track A inteiro)
$ git diff --stat 34cb479..3be5eed -- frontend Makefile
 Makefile                                        |   3 +
 frontend/package.json                           |   3 +
 frontend/src/components/ProcessingStatus.tsx    | 194 ++++---
 frontend/src/components/UploadDropzone.test.tsx | 179 +++++++
 frontend/src/components/UploadDropzone.tsx      |   8 +-
 frontend/src/components/ui/progress.test.tsx    |  44 ++
 frontend/src/components/ui/progress.tsx         |   5 +
 frontend/src/hooks/useDocumentStatus.test.ts    | 133 ++++-
 frontend/src/hooks/useDocumentStatus.ts         |   6 +-
 frontend/src/hooks/useNotices.ts                |  29 +-
 frontend/src/index.css                          |   7 +-
 frontend/src/lib/api.ts                         |  56 +-
 (+ package-lock.json)

$ make check
cd backend && uv run ruff check .        All checks passed!
cd frontend && npm run lint              exit 0
cd backend && uv run mypy app            Success: no issues found
cd frontend && npx tsc --noEmit          exit 0
cd backend && uv run lint-imports        (4 contratos)
cd backend && uv run pytest
  119 passed, 6 deselected in 7.13s
  Required test coverage of 90% reached. Total coverage: 98.98%
cd frontend && npm run test
  Test Files  6 passed (6)
       Tests  40 passed (40)
MAKE_CHECK_EXIT=0

$ make security
bandit -q -r app          (sem saída = sem achados)
pip-audit                 No known vulnerabilities found
npm audit --audit-level=high   found 0 vulnerabilities
MAKE_SECURITY_EXIT=0

# o gate morde? (três elos verificados separadamente)
$ npx vitest run --root=<temp com um teste falhando>
vitest com teste falhando -> exit=1
$ make -f <temp>  # receita: @true / @false / @echo NUNCA_CHEGA
make: *** [alvo] Error 1        (NUNCA_CHEGA não foi impresso)
$ grep -n -A4 "^test:" Makefile
22:test:
23-	cd backend && uv run pytest
24-	cd frontend && npm run test

# escopo travado, após o rework
$ grep -rnE "\.status ===? *[0-9]{3}|status *[=!]== *[0-9]{3}" frontend/src
(vazio)
$ grep -rnE "\balert\(|console\.(log|error|warn)" frontend/src | grep -v /ui/
(vazio)
$ grep -rn "fetch(" frontend/src --include=*.ts --include=*.tsx
frontend/src/lib/api.ts:60:    response = await fetch(`${BASE_URL}${path}`, {
$ grep -rniE "GEMINI_API_KEY|DATABASE_URL|/home/gabriel|AIza" frontend/src
(vazio)

# identificadores em pt-BR em código de produção
$ grep -rnE "\b(const|let|function|type)\s+(sem[A-Z]|documento|arquivo|campo|montar|...)" \
    frontend/src --include=*.ts --include=*.tsx | grep -v "\.test\."
frontend/src/lib/api.ts:57:  const semResposta = () =>
(uma única ocorrência)

$ git status --short
(vazio — árvore limpa ao final)
```

## 7. Itens da fase / DoD não atendidos

Nenhum item da fase. A DoD da `B.2` está inteira, inclusive os gates de backend
que na tentativa 1 eram `[—]`.

**Pendências que são da FEAT-0001, não desta fase** (registro para o fechamento):

- `A.1`, `A.2`, `A.3` e `A.4` estão com `RESSALVAS` na tentativa 1 e sem rework
  nesta branch — pela §2.11.3 continuam **reprovadas**. A spec não vai a
  `status: done` enquanto elas não fecharem.
- "Identificadores em inglês" (DoD global) — ver §5.1.
- O commit `34cb479` removeu um fragmento de 9 caracteres da `GEMINI_API_KEY` de
  um relatório da `A.1`. O fragmento **continua no histórico do git**, no commit
  pai. É matéria do Track A, mas vale a decisão do owner sobre rotacionar a chave
  antes de publicar o repositório.

## 8. Divergências entre o relatório e o código real

Nenhuma. As três afirmações centrais do §8 do relatório conferem:

- "`Makefile`, alvo `test:`, ganhou `cd frontend && npm run test`" → `Makefile:24`.
  **Confirma**, e provei que a linha reprova de verdade.
- "`notify.error` passou a despachar por `severity`" → `useNotices.ts:48-52` lê
  `severity` de `describeError` e escolhe canal e duração. **Confirma.**
- "o `clearTimeout` saiu do `finally` do `fetch` e passou a envolver o `request`
  inteiro" → `api.ts:56-93`. **Confirma**, e a reclassificação para
  `rede_indisponivel` no corpo abortado está lá (`api.ts:87-89`).
