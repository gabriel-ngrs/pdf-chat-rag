---
spec: 01-ingestao-pdf
fase: B.2
slug_fase: app-shell
status: rework
tentativa: 2
reprovacoes: 1
sha_inicial: f01ed27
sha_final: 3be5eed
range: f01ed27..3be5eed
---

# FASE B.2 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/pdf-chat-rag-trackB`, branch
> `feat/trackB-frontend`.

## 1. Resumo do que foi feito

A camada de dados do frontend passou a existir: tipos escritos a partir da §4.5,
identidade de sessão persistida, cliente HTTP que traduz qualquer falha para o
envelope `{code, message}` da §4.3 (inclusive quando a resposta não é JSON), e
os limites lidos de `GET /api/config` com estado degradado explícito quando essa
chamada falha. Sobre isso, a camada única de avisos: `notify.error(code)` produz
título, explicação e ação em pt-BR, sempre a mesma frase para a mesma falha.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `frontend/src/lib/types.ts` | Tipos do contrato de §4.5, escritos a partir da spec — não gerados do backend |
| `frontend/src/lib/session.ts` | UUID de sessão em `localStorage`, com fallback para contexto não-seguro |
| `frontend/src/lib/api.ts` | `fetch` com base `/api`, `X-Session-Id`, timeout e `ApiError` carregando o `code` |
| `frontend/src/lib/errors.ts` | Mapa `code → {título, mensagem, ação, severidade}` e `describeError()` |
| `frontend/src/lib/config.ts` | `loadConfig()` e o estado `loading / ready / degraded` |
| `frontend/src/components/Notices.tsx` | Ponto único onde os avisos aparecem (`Toaster` do shadcn) |
| `frontend/src/hooks/useNotices.ts` | API `notify.info / success / error(code)` |
| `frontend/src/lib/errors.test.ts` | Cobertura dos códigos da §4.3 e do fallback de código desconhecido |
| `frontend/src/lib/api.test.ts` | Sucesso, envelope de erro, resposta não-JSON e falha de rede |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `frontend/src/App.tsx` | Carrega a config no boot, monta os avisos e mostra os limites reais no passo 1 |
| `frontend/package.json` | `vitest` em devDependencies e script `test` |
| `frontend/package-lock.json` | Recommitado |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** O `Toaster` usado é o `src/components/ui/sonner.tsx`
gerado na `B.1` — nenhum componente de aviso foi escrito do zero. Os tokens de
cor, tipografia e raio vêm do design system da `B.1`; `Notices.tsx` não define
nenhuma cor própria. A `AppShell` foi reaproveitada sem alteração.

**Decisões de design:**

1. **Mapeamento por `code`, e `status` só para diagnóstico.** `ApiError` guarda
   o `status`, mas nenhuma decisão de mensagem o consulta — `describeError`
   recebe apenas o código. Verificado no teste do envelope 429: a UI mostra
   "Limite de uso atingido" porque o `code` é `limite_de_uso`, não porque o
   status é 429.
2. **Fallback de resposta não-JSON em dois pontos, não um.** Tanto o caminho de
   erro quanto o de sucesso podem receber HTML de um proxy; ambos viram
   `erro_interno` com mensagem genérica em vez de estourar um `SyntaxError`.
3. **Sem constante de limite no cliente.** O estado `degraded` não carrega
   números de fallback: um limite repetido aqui envelheceria em silêncio.
   Em estado degradado a validação local simplesmente não acontece.
4. **`notify.error(code, { message })`.** O override existe para o caso em que a
   interface sabe algo mais específico que o mapa (o tamanho real do arquivo
   recusado, na `B.3`). Título, ação e severidade continuam vindo do mapa.
5. **`api.ts` já expõe `fetchDocument` e `uploadDocument`.** As três funções de
   endpoint da §4.5 nasceram juntas porque `api.ts` é o arquivo declarado desta
   fase e as fases `B.3`/`B.4` **não** o declaram entre os seus — deixá-las para
   depois obrigaria a tocar um arquivo fora do escopo daquelas fases.

**Desvio declarado (fora da lista de "Arquivos alterados" da fase):**

- **`frontend/package.json` e `package-lock.json`.** A subseção "Testes" da fase
  exige dois testes (`describeError` cobre os códigos; resposta não-JSON não
  quebra o cliente) e o frontend não tinha nenhum runner. Foi acrescentado
  `vitest` e o script `npm run test`. **O `Makefile` não foi tocado** — ver
  item 1 da §9.

## 5. Comandos rodados + saídas reais

```text
# testes (frontend)
$ cd frontend && npm run test
 RUN  v4.1.10 /home/gabriel/Projetos/pdf-chat-rag-trackB/frontend
 Test Files  2 passed (2)
      Tests  10 passed (10)
   Duration  261ms

# type-check
$ cd frontend && npx tsc --noEmit
tsc ok   (exit 0)

# lint
$ cd frontend && npm run lint
> eslint src          (exit 0)

# container real, com o backend fora do ar (o nginx devolve 502 em HTML)
$ curl -s -o /dev/null -w "app HTTP %{http_code}\n" http://localhost:5173/
app HTTP 200
$ curl -s -o /dev/null -w "api HTTP %{http_code}\n" http://localhost:5173/api/config
api HTTP 502

# gate da fase: erro do backend vira aviso com título, mensagem e ação
$ python3 audit_notices.py http://localhost:5173
{
  "backend_fora_html_502": {
    "type": "error",
    "title": "Algo deu errado no servidor",
    "description": "Não consegui ler do servidor os limites de envio. Tente de novo em alguns instantes."
  },
  "envelope_429_limite_de_uso": {
    "type": "error",
    "title": "Limite de uso atingido",
    "description": "Não consegui ler do servidor os limites de envio. Espere cerca de um minuto e tente de novo."
  },
  "config_ok_sem_aviso": true,
  "limites_na_tela": true,
  "session_id_persistido": "7bc64f94-e1ea-4975-b14f-3fc215a09a8d"
}

# semântica de leitor de tela da região de avisos
$ python3 check_aria.py
{"tag": "section", "ariaLive": "polite", "ariaAtomic": "false", "ariaLabel": "Avisos alt+T"}
```

**Tentativa 2 — o gate agora roda inteiro.** Com o Track A mergeado em `dev`, os
alvos de backend deixaram de ser `[—]`:

```text
$ make check
cd backend && uv run ruff check .        # All checks passed!
cd frontend && npm run lint              # exit 0
cd backend && uv run mypy app            # Success
cd frontend && npx tsc --noEmit          # exit 0
cd backend && uv run lint-imports --config .importlinter
Contracts: 4 kept, 0 broken.
cd backend && uv run pytest
119 passed, 6 deselected · cobertura de core/ 98.98% (mínimo 90%)
cd frontend && npm run test
Test Files 6 passed (6) · Tests 40 passed (40)

MAKE_CHECK_EXIT=0

$ make security
bandit -q -r app                         # sem achados
pip-audit                                # No known vulnerabilities found
npm audit --audit-level=high             # found 0 vulnerabilities
MAKE_SECURITY_EXIT=0
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **`describeError` cobre todos os códigos da §4.3** — teste
  `errors.test.ts` afirma que os cinco códigos da spec estão em `ERROR_CODES`,
  que cada um tem título/mensagem/ação não vazios, que nenhum título se repete,
  e que código desconhecido cai em `erro_interno`. 10 testes verdes.
- [x] **Resposta não-JSON não quebra o cliente** — dois testes (`413` com HTML e
  `200` com HTML) e a verificação no container real, onde o nginx devolve um 502
  em HTML e o app mostra o aviso em vez de estourar.
- [x] **Mapeamento por `code`, não por status** — o envelope `429` com
  `code: "limite_de_uso"` produz o título "Limite de uso atingido"; o `502` sem
  envelope produz "Algo deu errado no servidor". Status diferentes, decisão
  tomada só pelo código.
- [x] **Critério de conclusão da fase** — erro forçado do backend aparece como
  aviso com título, mensagem e ação em pt-BR (screenshot e saída acima); lint e
  typecheck zero.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (10/10 nesta fase; 40/40 no frontend inteiro)
- [x] **`make check` inteiro retorna zero** — inclusive as duas suítes, que é o
  que o achado I-1 exigia
- [x] Escopo travado respeitado: nenhum mapeamento por status HTTP, nenhum limite
  duplicado em constante, nenhum `alert()`, nenhuma stack trace / corpo bruto /
  nome de exceção exibido, textos em pt-BR e identificadores em inglês
- [x] Nenhum segredo/PII em log, DTO ou exceção
- [x] Commits em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

Avaliação da tentativa 1: **RESSALVAS**, score 9,3. Zero BLOQUEANTES, um
IMPORTANTE e cinco sugestões.

### I-1 — testes do frontend fora de todo gate → **corrigido**

`Makefile`, alvo `test:`, ganhou `cd frontend && npm run test`. A razão que
motivou a recusa na tentativa 1 (arquivo compartilhado com o Track A, risco de
conflito de merge) deixou de existir: os dois tracks já vivem na mesma árvore em
`dev`. Agora `make check` roda as duas suítes e **falha se qualquer uma falhar**.

### Sugestões acatadas

- **S-1, `errors.ts:19` — `severity` nascia morto.** `notify.error` passou a
  despachar por ele: `CHANNEL_BY_SEVERITY` escolhe o canal do `sonner` e a
  duração a partir da severidade do mapa. Um código futuro marcado como aviso
  deixa de sair como erro vermelho.
- **S-3, `api.ts` — o timeout não cobria a leitura do corpo.** O `clearTimeout`
  saiu do `finally` do `fetch` e passou a envolver o `request` inteiro. Uma
  resposta que trava no corpo agora é cortada, e o corte vira
  `rede_indisponivel` em vez de `erro_interno` — é falta de resposta, não
  resposta estranha.
- **S-2, `useNotices()` não é um hook.** Mantido como está, com o comentário que
  o avaliador pediu: a indireção é deliberada, para trocar o `sonner` por um
  provider com estado sem mexer em todo componente que avisa algo.

### Sugestões avaliadas e não acatadas

- **S-4 (timeout de upload de 120 s) e S-5 (`api.ts` com os três endpoints)** —
  o avaliador concordou com as decisões originais e não pediu ação. Sem mudança.

## 9. Itens em aberto / dúvidas para o avaliador

1. **`api.ts` foi escrito com os três endpoints de uma vez** (config, documento,
   upload), antecipando o que `B.3` e `B.4` consomem. Avaliado na tentativa 1 e
   aceito (S-5). Registro para o histórico.
2. **`vitest`, `@testing-library/react` e `jsdom` são devDependencies novas**,
   fora da lista de arquivos original da fase. A subseção "Testes" da fase exige
   testes e o frontend não tinha runner; o desvio foi declarado e aceito na
   tentativa 1, e nesta tentativa cresceu com a testing-library, exigida pelos
   achados IMPORTANTES de `B.3` e `B.4`.
