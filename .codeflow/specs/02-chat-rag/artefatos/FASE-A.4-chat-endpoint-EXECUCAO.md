---
spec: 02-chat-rag
fase: A.4
slug_fase: chat-endpoint
status: rework
tentativa: 2
reprovacoes: 1
sha_inicial: 7fe47de9ac92e62523d38eab7366615b7d70d0bb
sha_final: e2b78250d82d3317abefa9359ac2a46d694a6105
range: 7fe47de..e2b7825
---

# FASE A.4 — Relatório de execução

## 1. Resumo do que foi feito

O chat passou a existir. `chat.py` orquestra o turno inteiro — histórico, persistência da
pergunta, condensação condicional, embedding, busca, limiar, recusa ou geração em
streaming, citações, persistência honesta — sem conhecer `fastapi`.
`api/conversations.py` expõe as três rotas de §4.4 e traduz os eventos em frames SSE.
`adapters/gemini.py` ganhou o `ChatClient` sobre a face **assíncrona** do SDK. Validado
ponta a ponta pelo `docker compose` contra a API real: resposta em streaming com citação
de página correta, pergunta de continuação resolvida e recusa sem chamar o LLM.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `backend/app/chat.py` | Orquestração do turno; emite `ChatEvent`, não frames |
| `backend/app/api/conversations.py` | `POST /conversations`, `POST .../messages` (SSE), `GET .../messages` |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/app/adapters/gemini.py` | +`ChatClient`, `GeminiChatClient`, `ChatQuotaError`, `ChatProviderError`, `_thinking_config` |
| `backend/app/api/schemas.py` | +`ConversationCreateRequest`, `ConversationResponse`, `QuestionRequest`, `CitationResponse`, `MessageResponse` |
| `backend/app/main.py` | Router de conversas + repositório de conversas e cliente de chat no lifespan |
| `backend/app/config.py` | Default do modelo de chat (ver §4) |
| `backend/app/errors.py` | +`DocumentNotReadyError` (`documento_nao_pronto`, `409`) |
| `backend/.importlinter` | `chat` declarado como camada irmã de `ingestion` |
| `backend/tests/test_gemini_adapter.py` | +12 testes de unidade do cliente de chat (rework, I-3) |
| `.env.example` | Modelo de chat que o provedor ainda atende (commit `3c89162`) |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `embed_query` não foi reimplementado — é consumido do adapter da
`FEAT-0001 A.3`. O backoff (`backoff_delay`), a sanitização (`sanitize_message`), a
classificação de status (`RETRYABLE_STATUS`, `QUOTA_STATUS`) e o envelope de erro são os
mesmos do adapter de embeddings. As rotas reusam `get_repository`, `get_embedder` e
`get_settings` de `api/documents.py`. Nenhum `GZipMiddleware` foi adicionado, e a
ausência ficou registrada em comentário no `main.py`.

### Decisões

- **`chat.py` não importa `fastapi`.** Ele produz `ChatEvent(name, data)`; quem serializa
  é a rota. É o que permite testar recusa, timeout, erro mid-stream e desconexão sem
  levantar servidor — e o que a fase `A.6` vai exercitar.
- **A rota puxa o primeiro evento antes de construir a resposta.** É a implementação de
  FR-11, e ela **é obrigatória**: verifiquei no ambiente que a forma idiomática do
  FastAPI (*path operation* gerador com `response_class=EventSourceResponse`) executa o
  gerador dentro de um task group **depois** de a resposta ter começado — uma exceção
  antes do primeiro `yield` estoura como `ExceptionGroup` e **não** passa pelos handlers
  de erro. Com o priming, o `429` pré-stream sai como HTTP `429` com `{code, message}`.
- **Frames por `fastapi.sse.format_sse_event`.** Como a resposta é devolvida pela rota (e
  não produzida pelo *path operation*), a codificação não é feita pela camada de
  roteamento; usar a função do próprio framework mantém o formato de fio idêntico ao que
  o parser do cliente espera, sem escrevê-lo à mão.
- **`Cache-Control: no-cache` e `X-Accel-Buffering: no` explícitos.** §4.3 diz que o
  `EventSourceResponse` já os define; **medi e ele não define** nesta forma de uso —
  entrega só o `Content-Type`. Os dois passaram a ser enviados pela rota.
- **Cliente de chat assíncrono** (`client.aio`), diferente do de embeddings, que é
  síncrono em thread. Uma thread não é cancelável: quando o usuário fecha a aba, o
  consumo de quota precisa parar de verdade (FR-12).
- **Duas tentativas de retry no chat**, contra cinco no embedding. O `429` do chat é
  quota por minuto; um backoff de segundos não a libera, e a NFR-1 dá cinco segundos até
  o primeiro token. Retry só na **abertura** do stream: depois do primeiro token,
  repetir duplicaria texto já exibido.
- **`truncated` começa verdadeiro** e só é desligado quando o laço chega ao fim sozinho.
  Desconexão, erro do provedor e cancelamento saem todos pelo `finally` com a marca
  correta, sem que cada caminho precise lembrar de marcá-la.
- **Turno que não gerou texto nenhum não vira mensagem.** Um balão vazio apareceria na
  tela e entraria na janela de histórico do turno seguinte como se fosse resposta; o
  fato fica no log (`chat.answer_empty`). Resposta **parcial** continua sendo persistida,
  com `truncated=true`, que é o que FR-9 pede.
- **`message_id` nulo quando a gravação falha.** Inventar um id faria a UI prender a
  mensagem a uma linha que não existe.

### DESVIOS

1. **`backend/.importlinter` e `backend/app/errors.py` foram alterados**, e não constam
   da lista de "arquivos alterados" da fase. Os dois estão em §4.7 como **REUSADO**
   ("consumido ou **estendido**, nunca duplicado"), e ambas as mudanças são forçadas por
   gates da própria fase: o contrato de camadas é `exhaustive = True`, então um módulo
   novo de primeiro nível (`app.chat`) **quebra `make arch`** se não tiver posição
   declarada; e o `409` com `documento_nao_pronto` de FR-1 precisa de uma classe de erro,
   que no projeto moram todas em `errors.py`.

2. **O modelo de chat da spec saiu do ar** — descoberto no gate desta fase, contra a API
   real. `gemini-2.5-flash` responde `404 NOT_FOUND` com a mensagem
   *"This model models/gemini-2.5-flash is no longer available to new users. Please
   update your code to use models/gemini-3.6-flash"*. O modelo **continua listado** em
   `models.list()`, então a falha só aparece na primeira geração. O default de
   `config.py` passou a `gemini-3.6-flash`.

3. **`thinking_budget=0` virou erro.** A geração 3.x responde `400 INVALID_ARGUMENT` a
   `thinking_budget=0` e expõe o mesmo controle como `thinking_level`. Medido:

   | modelo | config | resultado |
   |---|---|---|
   | `gemini-3.6-flash` | `temperature+max_output_tokens` | OK |
   | `gemini-3.6-flash` | `+ thinking_budget=0` | **400 INVALID_ARGUMENT** |
   | `gemini-3.6-flash` | `+ thinking_budget=128` | OK |
   | `gemini-3.6-flash` | `+ thinking_level=MINIMAL` | OK (1,58 s) |
   | `gemini-2.5-flash` | qualquer | **404 NOT_FOUND** |

   `GEMINI_THINKING_BUDGET=0` continua sendo a forma de pedir "sem raciocínio" no
   ambiente — **a variável e o contrato de configuração não mudaram**. O que mudou é a
   tradução: zero vira `ThinkingLevel.MINIMAL`; valor positivo continua indo como
   orçamento. A intenção da NFR-1 (mínimo de raciocínio, primeiro token o quanto antes)
   está preservada e medida abaixo.

4. **`.env.example` e a correção de FR-11 nasceram fora do commit desta fase** — o
   primeiro no `3c89162`, a segunda no `8a1c5f0`. Nesta segunda tentativa os dois estão
   **dentro** do `range`, que é o que a avaliação cobrou: o `sha_final` foi estendido e
   `sha_inicial` preservado. O detalhe do que cada um mudou está no §8.

## 5. Comandos rodados + saídas reais

```text
# lint
$ cd backend && uv run ruff check app tests
All checks passed!

# type-check
$ uv run mypy app
Success: no issues found in 23 source files

# arquitetura (com o módulo novo)
$ uv run lint-imports --config .importlinter
Camadas: main -> api -> (chat | ingestion) -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Sem ORM nem query builder KEPT
Contracts: 4 kept, 0 broken.

# suíte offline (na tentativa 1; os números do rework estão no §8)
$ uv run pytest -p no:cacheprovider -q
Required test coverage of 90% reached. Total coverage: 99.55%
213 passed, 17 deselected in 9.84s

# grep de segredo/PII no diff (esperado: 0)
$ git diff 7fe47de..9f0a2b1 | grep -ciE "AIza|api[_-]?key *=|postgresql://.*:.*@"
0
```

### Gate da fase — contra o `docker compose`, com a API real

Upload e ingestão do `Exemplo-YAITEC.pdf` pelo compose, documento `ready`; depois
`POST /api/conversations` e três perguntas na mesma conversa.

```text
$ curl -s http://localhost:8000/api/health
{"status":"ok","database":"ok"}

# 1) pergunta fundamentada
status: 200 | content-type: text/event-stream; charset=utf-8
cache-control: no-cache | x-accel-buffering: no
PRIMEIRO EVENTO em 2.21s
stream completo em 2.58s
[citations] {"citations": [{"page_number": 2, "snippet": "Ygor Alves, fundador e CEO,
  engenheiro eletricista pela UFPB e com mais de 5 anos de experiência em IA. …",
  "chunk_index": 6, "score": 0.761}, …]}
[done] {"message_id": 26, "truncated": false}
RESPOSTA: A YAITEC foi fundada por **Ygor Alves**. Ele é **engenheiro eletricista
  formado pela UFPB** (Universidade Federal da Paraíba) e possui mais de 5 anos de
  experiência em IA.
eventos token: 5

# 2) pergunta de continuação ("e quais deles são os clientes?")
PRIMEIRO EVENTO em 3.46s
RESPOSTA: … os clientes e parcerias da YAITEC são: ATC Analytics, ChatADV, Langflow,
  PagBank, StartStak.

# 3) pergunta fora do documento ("Qual a receita do bolo de cenoura…")
PRIMEIRO EVENTO em 0.39s
[citations] {"citations": []}
[done] {"message_id": 30, "truncated": false}
RESPOSTA: Não encontrei essa informação no documento enviado. …
eventos token: 1
```

Eventos de log do turno, do container:

```json
{"conversation_id":"48f4…","question_len":44,"event":"chat.turn_started","request_id":"adbc…"}
{"conversation_id":"48f4…","candidates":5,"above_threshold":5,"top_score":0.761,"duration_ms":660,"event":"chat.retrieved","request_id":"adbc…"}
{"conversation_id":"48f4…","token_count":5,"truncated":false,"duration_ms":2540,"event":"chat.generated","request_id":"adbc…"}
{"conversation_id":"48f4…","used_llm":true,"fallback":false,"duration_ms":1481,"event":"chat.condensed","request_id":"56fd…"}
{"conversation_id":"48f4…","candidates":5,"above_threshold":0,"top_score":0.507,"duration_ms":334,"event":"chat.retrieved","request_id":"a864…"}
{"conversation_id":"48f4…","top_score":0.507,"event":"chat.refused","request_id":"a864…"}
```

Caminhos de erro, também pelo compose:

```text
$ POST /api/conversations com documento em processamento
HTTP/1.1 409 Conflict
{"code":"documento_nao_pronto","message":"O documento ainda está sendo processado. …"}

$ POST /api/conversations/<uuid inexistente>/messages
404 {"code":"nao_encontrado","message":"Conversa não encontrada."}

$ POST .../messages com {"question":"   "}
422 {"code":"arquivo_invalido","message":"Os dados enviados são inválidos. …"}

$ GET /api/conversations/<id>/messages
25 user      False 0  Quem fundou a YAITEC e qual a formação dele?
26 assistant False 5  A YAITEC foi fundada por **Ygor Alves** …
27 user      False 0  e quais deles são os clientes?
28 assistant False 5  Com base nos trechos fornecidos, os clientes … 
29 user      False 0  Qual a receita do bolo de cenoura …
30 assistant False 0  Não encontrei essa informação no documento enviado. …
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-1** — `409` com `documento_nao_pronto` para documento em processamento (saída acima).
- [x] **AC-2** — cinco eventos `token` concatenados formam a resposta; `content-type: text/event-stream`.
- [x] **AC-8** — pergunta fora do documento: recusa em 0,39 s, `citations: []`, `chat.refused` no log, **nenhum** `chat.generated` (o `stream_answer` não foi chamado).
- [x] **AC-10** — evento `citations` com `page_number`, `snippet` recortado, `chunk_index` e `score`.
- [x] **AC-11** — histórico com as seis mensagens na ordem, citações presas às respostas, coluna `truncated` presente.
- [x] **AC-15** — `chat.turn_started`, `chat.condensed`, `chat.retrieved`, `chat.refused` e `chat.generated`, todos com `conversation_id` e `request_id`.
- [x] **AC-23 (NFR-1)** — primeiro evento em **2,21 s** e **3,46 s** (com condensação), ambos ≤ 5 s, com raciocínio no nível mínimo.
- [x] **AC-24** — `make arch` passa com o módulo novo, que precisou ser declarado no contrato (`exhaustive`).
- [x] **FR-3/FR-4 em produção** — `chat.condensed` com `used_llm: true, fallback: false` na pergunta de continuação, e a resposta correta prova que a query condensada recuperou a página certa.

## 7. Definition of Done da fase

- [x] Testes verdes: 260 offline e 19 sob o marker `db`. Os de integração do chat são escopo da `A.6`; os **de unidade do adapter** passaram a existir nesta tentativa (I-3)
- [x] `ruff`, `mypy`, `lint-imports` e `pytest` zerados
- [x] Escopo travado respeitado: nenhuma chamada ao Gemini fora do adapter; resposta **não** bufferizada; resposta parcial nunca gravada como completa; nenhum `GZipMiddleware`; `embed_query` reusado; nem prompt integral nem pergunta completa em nível `info` (só `question_len`)
- [x] Nenhum segredo em log, resposta ou evento SSE
- [x] Commit em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

A avaliação da tentativa 1 deu **RESSALVAS** com três achados IMPORTANTES. Os três estão
fechados, e o `range` desta tentativa contém todos os commits envolvidos.

### I-1 — o `range` descrevia código quebrado

Não é correção de código: é correção de artefato, e a avaliação tem razão no argumento.
Auditando `7fe47de..9f0a2b1` o avaliador lia um AC-12 quebrado, e só sabia do conserto
porque o relatório contava — que é exatamente a dependência que a avaliação em chat
zerado existe para não ter. O `sha_final` foi estendido até conter os dois commits que
faltavam, com o `sha_inicial` intacto:

- **`8a1c5f0`** — a falha do provedor na **abertura** do stream voltou a caber no
  envelope HTTP. A versão da tentativa 1 tratava toda `AppError` como erro mid-stream:
  virava evento `error` e a rota entregava `200 text/event-stream`, quando FR-11 exige
  `{code, message}` com o status. Como o `429` do chat estoura justamente na abertura, o
  caminho quebrado era o caso comum. A decisão passou a ser tomada pelo único fato que
  importa — se algum token já saiu —, e o `phase` do log diz a verdade nos dois casos.
  No mesmo commit: o iterador do provedor passou a ser fechado explicitamente (FR-12
  determinístico) e `TOKEN_EVENT` ganhou `# nosec B105`, porque o `bandit` a lia como
  credencial embutida e derrubava `make security` por falso positivo.
- **`3c89162`** — o `.env.example` passou a documentar o modelo de chat que o provedor
  ainda atende.

### I-2 — `CHAT_TIMEOUT_SECONDS` era configuração morta (commit `f1f8be7`)

A variável existia em `config.py` e no `.env.example` e não tinha consumidor nenhum:
`generate` tinha prazo, `stream_answer` não tinha nenhum. Um provedor que abrisse o
stream e parasse de emitir prenderia o turno até o `proxy_read_timeout` de 300 s do
nginx derrubar a conexão — e só então a resposta parcial seria gravada, quatro minutos
depois.

Escolhi **consumir** a variável, e não removê-la. O prazo vale para o turno inteiro,
contado da abertura do stream (de modo que o tempo gasto para abrir também conte, que é
o que alguém entende ao ler "60 s" num arquivo de configuração), e o estouro vira
`ChatProviderError`. Quem decide se isso sai como envelope HTTP ou como evento `error`
continua sendo `app.chat`, pelo critério de FR-11 — nada de novo precisou ser ensinado à
orquestração.

A implementação ficou no adapter, e não em `chat.py`, porque é o adapter que já é dono
dos prazos do provedor (`generate` já recebia um) e porque o protocolo `ChatClient` de
§4.2 não tem parâmetro de timeout em `stream_answer` — respeitá-lo evitou mudar o
contrato que o dublê da `A.6` implementa.

### I-3 — o `GeminiChatClient` não tinha teste de unidade (commit `c64104f`)

Doze testes novos em `tests/test_gemini_adapter.py`, sobre um transporte assíncrono
falso escrito ali mesmo (`FakeAsyncModels`/`FakeAsyncClient`) — em `tests/fakes.py` ele
seria dublê de outra fase. Cobrem exatamente o que a avaliação listou:

| Lacuna apontada | Teste |
|---|---|
| `_thinking_config` com orçamento 0 e positivo | `test_orcamento_zero_chega_ao_provedor_como_nivel_minimo`, `test_orcamento_positivo_continua_chegando_como_orcamento` |
| caminho feliz de `generate` | `test_generate_devolve_o_texto_podado_com_o_teto_da_condensacao` |
| retry por falha transitória | `test_falha_transitoria_na_abertura_do_stream_e_re_tentada_uma_vez`, `test_falha_transitoria_persistente_esgota_as_tentativas` |
| desistência em status não-retentável | `test_status_nao_retentavel_desiste_na_primeira_tentativa` |
| `chunk.text` nulo filtrado (§4.2) | `test_stream_descarta_pedaco_sem_texto_e_preserva_a_ordem` |
| quota do chat distinta de falha de provedor | `test_quota_do_chat_vira_erro_de_quota_e_nao_de_provedor` |
| prazo do turno (I-2) | `test_provedor_que_emudece_estoura_o_prazo_do_turno` |
| fechamento do iterador (FR-12) | `test_stream_fecha_o_iterador_do_provedor_ao_terminar` |
| chave ausente | `test_chave_ausente_falha_antes_de_qualquer_chamada_de_chat` |

A asserção da tradução do raciocínio é sobre **o que chegou ao transporte**, e não sobre
a função privada: é lá que a diferença entre `thinking_level` e `thinking_budget` existe.

Cobertura de `app/adapters/gemini.py`: **90% → 97%** (de 12 linhas descobertas para 3).

### Sugestões da avaliação que também foram acatadas

O texto de **NFR-1**, **AC-23**, §4.2 e §4.8 da spec cobrava `thinking_budget=0`, e
`.codeflow/manifest.md` ainda anunciava `gemini-2.5-flash` para geração. Os dois foram
corrigidos no commit `e2b7825`, junto com o limiar de FR-3 (`< 12` → `< 4` palavras) que
a avaliação da `A.2` confirmou ser erro da spec, não da implementação.

### Saídas dos gates depois do rework

```text
$ cd backend && uv run ruff check app tests
All checks passed!

$ uv run mypy app
Success: no issues found in 23 source files

$ uv run pytest -p no:cacheprovider -q
Required test coverage of 90% reached. Total coverage: 99.55%
260 passed, 19 deselected in 11.49s

$ uv run pytest -m db -p no:cacheprovider --no-cov -q
19 passed, 260 deselected in 1.86s

$ uv run bandit -q -r app
(sem saída)                                   exit 0

$ uv run pytest --cov=app.adapters.gemini --cov-report=term-missing \
      tests/test_gemini_adapter.py tests/test_chat_security.py
app/adapters/gemini.py       200      3     36      4    97%   366, 384, 476->exit, 568
```

## 9. Itens em aberto / dúvidas para o avaliador

- **A tentativa 1 foi commitada sem teste de unidade do adapter**, apostando que o
  fatiamento da spec cobriria a lacuna pela `A.6`. A avaliação mostrou que não cobria:
  `tests/test_gemini_adapter.py` não pertence a fase nenhuma do Track A, então a lacuna
  era desta. Fechada nesta tentativa (§8, I-3).
- **Os desvios 2 e 3 (§4) são mudanças de comportamento externo.** O `manifest.md` e o
  texto de NFR-1/AC-23 da spec foram corrigidos nesta tentativa (commit `e2b7825`); o
  `README.md` ainda não menciona modelo algum, e é entregável da fase `B.5`. Quem já tem
  um `.env` local **precisa atualizá-lo** — o `.env` não foi tocado, por ser arquivo
  protegido pela constitution. A validação pelo compose rodou com o modelo passado por
  variável de ambiente no container (`docker compose run -e GEMINI_CHAT_MODEL=…`),
  justamente para não editar o `.env`.
- **A latência medida inclui a rede real** e ficou bem dentro do teto, mas foi medida
  numa conversa com histórico curto. Com a janela cheia (6 mensagens) o prompt cresce e
  o primeiro token deve demorar um pouco mais.
- **O modelo às vezes cita páginas a mais no texto** ("páginas 2 e 3") quando os dois
  trechos vêm da mesma página. As citações **estruturadas** — que são o contrato — vieram
  corretas. É ruído de geração, não de fundamentação, e o prompt já instrui a citar a
  página de cada informação.
- **A rede de segurança do `_frames`** converte uma exceção não prevista em evento
  `error` com fechamento limpo. Não foi exercitada contra o provedor real (não houve
  como provocá-la); a `A.6` a cobre offline.
- **O gate contra o compose foi executado antes da correção do commit `8a1c5f0`.** Os
  caminhos validados lá (resposta fundamentada, pergunta de continuação, recusa, `409`,
  `404`, `422`, histórico) não são afetados por ela — nenhum deles passa pelo caminho de
  falha do provedor. O caminho corrigido é provado offline pela `A.6`
  (`test_quota_na_abertura_do_stream_sai_como_http_429`).
