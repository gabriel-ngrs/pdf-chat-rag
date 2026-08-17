---
spec: 02-chat-rag
fase: A.4
slug_fase: chat-endpoint
tentativa: 1
veredito: RESSALVAS
score: 8.8
threshold: 8.5
range_avaliado: 7fe47de9ac92e62523d38eab7366615b7d70d0bb..9f0a2b1a512b25f8294edca99971a265552fc355
---

# FASE A.4 — Avaliação independente

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 8.8 / threshold 8.5

Zero BLOQUEANTES — o código **na ponta da branch** cumpre todos os ACs da fase, e
eu verifiquei isso rodando a suíte. Três IMPORTANTES, todos sobre o que a fase
deixou de fora do próprio perímetro:

1. o `range` desta fase **não contém** o commit que conserta o defeito de FR-11
   que ela própria introduziu (§4 I-1);
2. `CHAT_TIMEOUT_SECONDS` é configuração morta — nada no código a consome, e o
   streaming não tem prazo de morte (§4 I-2);
3. o `GeminiChatClient` — inclusive o `_thinking_config`, que é a peça nova
   inteira desta fase — não tem teste de unidade em lugar nenhum (§4 I-3).

O desenho, em contrapartida, é o ponto alto do Track A: `chat.py` orquestra o
turno inteiro sem conhecer `fastapi`, e o *priming* do primeiro evento na rota é
a solução correta para FR-11.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 3 | Escopo travado 100% respeitado (sem Gemini fora do adapter, sem buffer, sem `GZipMiddleware` — `main.py:6-8`, sem prompt/pergunta em log — só `question_len` em `chat.py:96`); desconta: a fase declara nove `Testes` e entregou **zero** no seu range, e o AC-12 estava quebrado no commit que ela fecha |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `chat.py` não importa `fastapi`; a rota é quem serializa (`conversations.py:161-186`); `.importlinter` passou a declarar `chat : ingestion` como irmãs, com `exhaustive = True` mantido — `Contracts: 4 kept, 0 broken` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `_fail_chat` sanitiza e usa `raise ... from None` (`gemini.py:545-558`); `MAX_QUESTION_LENGTH` + `strip_whitespace` validam no servidor (`schemas.py:76-86`); a chave não aparece em cinco caminhos de erro (`test_chat_security.py:284-386`) |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `backoff_delay`, `sanitize_message`, `RETRYABLE_STATUS`, `QUOTA_STATUS`, `embed_query`, `get_repository`/`get_embedder`/`get_settings` — todos consumidos, nenhum reescrito |
| 5 | Padrões de domínio/aplicação | 2 | 4 | `truncated` começando `True` e sendo desligado só pelo `else` do laço (`chat.py:267,283-284`) é o padrão certo; desconta: `CHAT_TIMEOUT_SECONDS` documentado e não consumido (§4 I-2) |
| 6 | Local e nomes dos arquivos | 2 | 5 | Os dois arquivos novos e os quatro alterados estão onde a fase manda; `errors.py` e `.importlinter` fora da lista, mas são REUSADO em §4.7 e a mudança é forçada pelos gates da própria fase |
| 7 | Qualidade de código | 2 | 5 | Funções curtas e nomeadas pela decisão que tomam (`_prepare`, `_condense`, `_refuse`, `_answer`); docstrings dizendo por quê; `mypy --strict` limpo em 23 arquivos |
| 8 | Testes e cobertura | 2 | 3 | Nenhum teste no range da fase; hoje `app/chat.py` está em 96% e `app/api/conversations.py` em 82% graças à `A.6`, mas `app/adapters/gemini.py` deixa descobertos justamente os trechos novos (§6) |

Score = (3·3 + 5·3 + 5·3 + 5·3 + 4·2 + 5·2 + 5·2 + 3·2) / 20 × 2 = **8.8**

## 3. Achados BLOQUEANTES

Nenhum. Registro explícito: o defeito de FR-11 que existia no commit `9f0a2b1`
**está corrigido** no `8a1c5f0`, e eu confirmei o comportamento correto rodando
`test_quota_na_abertura_do_stream_sai_como_http_429` (passa) e lendo
`chat.py:297-304`.

## 4. Achados IMPORTANTES

### I-1 — o `range` da fase descreve código quebrado; a correção mora no range da `A.6`

`FASE-A.4-chat-endpoint-EXECUCAO.md:10` declara `range: 7fe47de..9f0a2b1`. Nesse
range, `app/chat.py::_answer` tratava **toda** `AppError` como erro mid-stream, e
a rota devolvia `HTTP 200 text/event-stream` com um frame `error` — quando FR-11
exige o envelope `{code, message}` com o status. Como o `429` do chat estoura na
abertura do stream (a própria spec chama isso de "o caso comum"), a metade
`pre_stream` estava morta.

A correção está no commit `8a1c5f0`, que pertence ao range da `A.6`
(`77175cd..37f27e7`). O mesmo vale para o `.env.example` desta fase, que foi no
`3c89162` — commit que **não está no range de fase nenhuma**.

**Por que isto importa e não é burocracia:** o `range` é o que este workflow
audita. Auditando `7fe47de..9f0a2b1` eu leria um AC-12 quebrado; só sei que ele
foi consertado porque **o relatório me contou** — que é exatamente a dependência
que a avaliação independente existe para não ter. O caminho previsto pelo
pipeline (`ARTIFACTS_SPEC` §2.9/§2.11) era um **rework da `A.4`**: `tentativa: 2`,
`sha_inicial` preservado, `sha_final` estendido até conter o conserto.

**Correção sugerida:** reemitir `FASE-A.4-chat-endpoint-EXECUCAO.md` como
`status: rework`, `tentativa: 2`, `reprovacoes: 1`, `sha_inicial: 7fe47de…`
inalterado e `sha_final` na ponta que contenha `8a1c5f0` e `3c89162`; a seção
"O que mudou nesta tentativa" recebe o que já está escrito hoje no §4 desvio 5.
Nenhuma linha de código muda. Fecha também o I-1 da `A.6`.

### I-2 — `backend/app/config.py:47` + `.env.example:45`: `CHAT_TIMEOUT_SECONDS` é configuração morta, e o streaming não tem prazo

```text
$ grep -rn "chat_timeout_seconds\|CHAT_TIMEOUT" --include=*.py --include=*.toml backend/
backend/app/config.py:47:    chat_timeout_seconds: int = 60
$ grep -n "CHAT_TIMEOUT" .env.example
45:CHAT_TIMEOUT_SECONDS=60
```

Nenhum consumidor. `generate` tem prazo (`gemini.py:438`, via
`condense_timeout_seconds`), mas `stream_answer` (`gemini.py:440-464`) não tem nenhum: se o provedor abrir o stream e parar de
emitir, o turno fica preso até o `proxy_read_timeout 300s` do nginx derrubar a
conexão — e a mensagem parcial só é gravada quando isso acontece.

Um arquivo de configuração que promete um teto de 60 s e não entrega nenhum é
pior que a ausência da variável: quem opera acredita que existe um limite.

**Correção sugerida:** consumir a variável — envolver o laço de
`app/chat.py::_answer` (ou `_open_stream` + o `async for`) num prazo derivado de
`settings.chat_timeout_seconds`, tratando o estouro como erro mid-stream se algum
token já saiu e pré-stream se não — **ou** remover a variável de `config.py` e do
`.env.example`. Uma das duas; a terceira opção (deixar como está) é a única
inaceitável.

### I-3 — `backend/app/adapters/gemini.py:396-565`: o `GeminiChatClient` não tem teste de unidade

`tests/test_gemini_adapter.py` tem 32 testes e **nenhum** toca o cliente de chat.
O adapter só é exercitado de lado, pelos testes de vazamento de
`test_chat_security.py`, cujo alvo é a sanitização. A cobertura mostra o buraco:

```text
app/adapters/gemini.py   189   12   38   8   90%   215, 475, 501-504, 536-539, ...
```

Ficam sem nenhum teste, todos código **novo desta fase**:

- **`215` — `_thinking_config` com orçamento positivo.** É a peça central do
  desvio 3 do relatório (a tradução de `GEMINI_THINKING_BUDGET` para o que a
  geração 3.x aceita). O ramo `<= 0` é o default e nem esse tem asserção direta.
- **`475` — o caminho feliz de `generate`.** A condensação por LLM nunca foi
  exercitada contra o adapter real; só contra o `FakeChatClient`.
- **`501-504` — o retry por falha transitória** (`TimeoutError`/`OSError`/
  `httpx.TransportError`) no chat, e a desistência por status não-retentável.
- **`536-539` — a criação preguiçosa do cliente e o `MissingApiKeyError`.**

Some-se o que a §4.2 da spec manda explicitamente e não tem teste: *"O `chunk.text`
do SDK pode vir `None` — filtrar antes de emitir"* (`gemini.py:454-456`). É o
filtro que impede a UI de escrever `null` no meio da frase, e nada garante que
ele continue lá.

A rule `testing` é direta: "todo código novo deve ter teste correspondente".
`test_gemini_adapter.py` não está na lista de arquivos de nenhuma fase do Track A,
então esta lacuna não é da `A.6` — é desta fase.

**Correção sugerida:** acrescentar a `tests/test_gemini_adapter.py`, sobre o
`StubGenaiClient` que já existe: (a) `_thinking_config(0)` produz
`thinking_level=MINIMAL` e `_thinking_config(128)` produz `thinking_budget=128`;
(b) `stream_answer` descarta pedaço com `text=None` e emite os demais na ordem;
(c) `generate` devolve o texto podado; (d) `TimeoutError` na abertura re-tenta uma
vez e depois vira `ChatProviderError`; (e) status não-retentável não re-tenta.

## 5. Sugestões

- **NFR-1 e AC-23 ficaram desatualizados pelo provedor.** A spec cobra
  `thinking_budget=0`; o código manda `thinking_level=MINIMAL` porque a geração
  3.x recusa o zero com `400`. A **intenção** de NFR-1 está preservada e medida
  (2,21 s até o primeiro evento), a variável de ambiente não mudou, e o desvio
  está documentado em três lugares. **Ação para o owner:** atualizar o texto de
  NFR-1/AC-23 na spec e a linha de `.codeflow/manifest.md:17`, que ainda diz
  `gemini-2.5-flash para geração`.
- **`chat.py:274` — o pedaço em voo é descartado na desconexão.** O `async for`
  já puxou `piece` quando a checagem roda, e ele é jogado fora sem ser emitido
  nem contado. É inerente à forma do laço, o custo é um token, e o teste
  documenta o comportamento. Fica registrado.
- **`conversations.py:56-59,64-67` — as guardas `RuntimeError` do lifespan não
  têm teste.** São defesa contra erro de fiação, não caminho de usuário. Baixa
  prioridade.
- **`chat.py:204` — o ramo "condensação devolveu string vazia → fallback" não tem
  teste.** É um `if` de uma linha, mas é o único caminho de fallback que não é o
  timeout. Uma linha no `FakeChatClient` (`condensed=""`) cobre.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 9f0a2b1 HEAD && echo OK
OK

$ make check
cd backend && uv run ruff check .    → All checks passed!
cd backend && uv run mypy app        → Success: no issues found in 23 source files
cd backend && uv run lint-imports --config .importlinter
Camadas: main -> api -> (chat | ingestion) -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Sem ORM nem query builder KEPT
Contracts: 4 kept, 0 broken.
tests/test_chat_api.py ...................                               [  8%]
Required test coverage of 90% reached. Total coverage: 99.55%
248 passed, 17 deselected in 11.67s
Test Files  10 passed (10) | Tests  75 passed (75)
[exited with code 0]

$ make security
bandit -q -r app       → (sem saída)
pip-audit              → No known vulnerabilities found
npm audit --audit-level=high → found 0 vulnerabilities
SEC_EXIT=0
```

Cobertura fora de `core/` (fora do piso de 90%, medida por mim para localizar o
I-3):

```text
Name                         Stmts   Miss Branch BrPart  Cover   Missing
app/adapters/gemini.py         189     12     38      8    90%   215, 366, 384,
                                                                 453->463, 455->453,
                                                                 464->exit, 475,
                                                                 501-504, 536-539
app/api/conversations.py        72     10     16      2    82%   56-59, 64-67, 140, 156
app/chat.py                    131      4     24      2    96%   204, 361-363, 374->exit
```

Configuração morta:

```text
$ grep -rn "chat_timeout_seconds\|CHAT_TIMEOUT" --include=*.py --include=*.toml backend/
backend/app/config.py:47:    chat_timeout_seconds: int = 60
```

**Não re-executado por mim:** o gate contra o `docker compose` com a API real
(AC-23, primeiro token ≤ 5 s). Não há `.env` nesta árvore de trabalho — o
`docker compose config` falha com *"required variable GEMINI_API_KEY is missing a
value"* —, então não há como levantar o backend nem gastar quota. As evidências
do relatório (2,21 s / 3,46 s / 0,39 s, com citação de página correta) ficam
**não verificadas independentemente**; o que verifiquei é que todos os caminhos
que elas exercitam têm prova automatizada offline na `A.6`.

## 7. Itens da fase / DoD não atendidos

- **A linha `Testes:` da fase** (nove ACs) não foi entregue no range da fase. A
  justificativa — a `A.6` declara como seus os arquivos `test_chat_api.py` e
  `test_chat_security.py` — é legítima e eu a aceito para os testes de
  integração. Ela **não** cobre `test_gemini_adapter.py`, que não pertence a
  nenhuma fase e ficou sem os testes do I-3.
- **`Passo 1` da fase** ("reusando backoff e sanitização já existentes, com
  `thinking_budget=0`") foi cumprido em substância, com a tradução forçada pelo
  provedor. Ver §5.
- **Critério de conclusão** (streaming pelo compose, primeiro token ≤ 5 s):
  atendido pelo executor, não reproduzível por mim (§6).
- DoD global: `make check` zero ✓, `make security` sem achado ✓, cobertura de
  `core/` 99,55% ✓.

## 8. Divergências entre o relatório e o código real

- **Nenhuma divergência de conteúdo.** As nove decisões de §4 do relatório batem
  com o código: `chat.py` sem `fastapi` ✓, priming do primeiro evento
  (`conversations.py:136-142`) ✓, `format_sse_event` do framework ✓,
  `Cache-Control`/`X-Accel-Buffering` explícitos (`conversations.py:51`) ✓,
  cliente assíncrono `client.aio` ✓, `CHAT_MAX_ATTEMPTS = 2` ✓, `truncated`
  começando `True` ✓, turno vazio não virando mensagem ✓, `message_id` nulo ✓.
- **Divergência de perímetro, não de fato:** o relatório declara `range:
  7fe47de..9f0a2b1` e depois explica, em prosa, que duas partes essenciais da
  fase estão fora dele. O frontmatter é o que as ferramentas leem; a prosa não é.
  É o I-1.
