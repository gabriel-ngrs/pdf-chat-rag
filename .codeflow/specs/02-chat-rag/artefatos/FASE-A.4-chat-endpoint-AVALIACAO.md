---
spec: 02-chat-rag
fase: A.4
slug_fase: chat-endpoint
tentativa: 2
veredito: RESSALVAS
score: 9.6
threshold: 8.5
range_avaliado: 7fe47de9ac92e62523d38eab7366615b7d70d0bb..e2b78250d82d3317abefa9359ac2a46d694a6105
---

# FASE A.4 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 9.6 / threshold 8.5

Zero BLOQUEANTES. Os **três** achados IMPORTANTES da tentativa 1 estão fechados,
e conferi os três:

- **I-1** — o `range` agora vai até `e2b7825`, que contém `8a1c5f0` **e**
  `3c89162` (ancestralidade verificada, §6). O artefato voltou a descrever o
  código que ele aprova.
- **I-2** — `CHAT_TIMEOUT_SECONDS` tem consumidor. Verifiquei o comportamento
  eu mesmo: com prazo de 1 s e um provedor que abre o stream e emudece, o turno
  morre em **1,00 s** com `ChatProviderError` e o iterador é fechado (§6).
- **I-3** — 12 testes novos no adapter; cobertura de `gemini.py` **90% → 97%**,
  medida por mim.

**Um IMPORTANTE novo**, e é estreito: o teste que deveria proteger a correção do
I-2 **não protege o trecho que a correção acrescentou**. Ele roda com
`chat_timeout_seconds=0`, e nesse regime o prazo estoura na **abertura** do
stream — `generate_content_stream` nem chega a ser chamado. O `stall=True` do
dublê é inerte ali, e a linha que faz o prazo valer **entre pedaços** poderia ser
apagada sem que a suíte reclamasse. Provei as duas afirmações (§4, §6).

O código está certo — isso eu verifiquei. O que falta é o teste morder, no mesmo
padrão que a `A.3` aplicou nesta mesma rodada.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | `range` coerente com o código aprovado (§6); escopo travado intacto — sem Gemini fora do adapter, sem buffer, sem `GZipMiddleware`, `embed_query` reusado, nem prompt nem pergunta em `info` |
| 2 | Arquitetura e direção de dependências | 3 | 5 | O prazo ficou no adapter, dono dos prazos do provedor, sem mexer no protocolo `ChatClient` de §4.2 — decisão certa: o dublê da `A.6` não precisou mudar; `Contracts: 4 kept, 0 broken` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | A mensagem do estouro não carrega prompt nem chave (`gemini.py:491-493`); sanitização e `raise ... from None` intactos; `make security` exit 0 |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `_with_deadline` reusa `_fail_chat`, que reusa a classificação de status já existente; nenhum mapa de erro novo |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Prazo do **turno**, contado da abertura, é a leitura que um operador faz de "60 s" no arquivo de configuração; o estouro vira `ChatProviderError` e quem escolhe entre envelope HTTP e evento `error` continua sendo `app.chat` (FR-11) |
| 6 | Local e nomes dos arquivos | 2 | 5 | `gemini.py` e `test_gemini_adapter.py`; o transporte falso mora no próprio arquivo de teste, e não em `fakes.py`, com a razão registrada |
| 7 | Qualidade de código | 2 | 5 | `_with_deadline` tem cinco linhas e uma responsabilidade; docstrings dizem por quê; `mypy --strict` limpo |
| 8 | Testes e cobertura | 2 | 3 | 12 testes novos, todos com asserção real sobre o que chegou ao transporte; cobertura 90→97%; desconta pesado: o único teste do prazo não exercita o trecho que a correção do I-2 acrescentou (§4) |

Score = (5·3 + 5·3 + 5·3 + 5·3 + 5·2 + 5·2 + 5·2 + 3·2) / 20 × 2 = **9.6**

## 4. Achados IMPORTANTES

### I-1 (novo) — `backend/tests/test_gemini_adapter.py:657` — o teste do prazo não cobre o trecho que a correção do I-2 acrescentou

```python
async def test_provedor_que_emudece_estoura_o_prazo_do_turno() -> None:
    """...um provedor que abre o stream e para de emitir..."""
    models = FakeAsyncModels(stall=True)
    with pytest.raises(ChatProviderError):
        await coletar(build_chat_client(models, timeout=0))
```

Com `timeout=0`, `deadline` (`gemini.py:458`) é o instante atual, e o **primeiro**
`_with_deadline` — o da abertura, `gemini.py:459` — já estoura. O `asyncio.wait_for`
com prazo zero cancela a corrotina antes de ela rodar, então `generate_content_stream`
não chega a ser chamado e o `stall=True` do dublê nunca é alcançado.

**Medido por mim, com o próprio dublê da suíte:**

```text
(a) timeout=0 -> ChatProviderError | generate_content_stream chamado? False | closed=False
(b) timeout=1 -> ChatProviderError apos 1.00s | generate_content_stream chamado? True | closed=True
```

A linha (b) é o cenário que a docstring descreve, e ele **funciona** — o código
está correto. A linha (a) é o que a suíte roda: prova o prazo da abertura, não o
prazo entre pedaços.

**Consequência concreta:** apagar `chunk = await self._with_deadline(anext(stream),
deadline)` (`gemini.py:463`) e voltar ao `async for` deixaria a suíte **inteira
verde** — conferi que `stall` é usado num único teste, e é este. O defeito que o
I-2 descreveu (provedor que abre e emudece prende o turno até o nginx derrubar)
voltaria sem nenhum sinal. É o mesmo padrão do achado original: uma promessa sem
mecanismo que a sustente — desta vez do lado do teste.

**Correção sugerida** — um caractere de código e uma asserção:

```python
    models = FakeAsyncModels(stall=True)
    with pytest.raises(ChatProviderError):
        await coletar(build_chat_client(models, timeout=0.05))
    assert models.models_pedidos, "o prazo precisa estourar depois de o stream abrir"
    assert models.closed, "o iterador do provedor precisa ser fechado no estouro"
```

`chat_timeout_seconds` é `int` em `Settings`, então ou o teste passa `timeout=1`
(um segundo de suíte, aceitável para o único teste que precisa dele) ou o campo
vira `float` — o que também tornaria o prazo ajustável com granularidade fina em
produção. A escolha é sua; o que não pode continuar é o `timeout=0`.

Vale a pena manter **os dois** testes: o de prazo zero prova a metade da abertura,
que também é comportamento real.

## 5. Sugestões

- **`.env.example:45` — `CHAT_TIMEOUT_SECONDS=60` continua sem comentário.**
  Agora que a variável faz alguma coisa, ela merece a mesma linha de explicação
  que `SIMILARITY_THRESHOLD` e `CHUNK_SIZE` têm no arquivo: que ela limita o
  turno inteiro, contado da abertura do stream, e que estourá-la vira erro de
  provedor. É o arquivo que quem clona lê.
- **`gemini.py:479-493` — `_with_deadline` engole `TimeoutError` de qualquer
  origem.** Se o `awaitable` interno levantar `TimeoutError` por conta própria
  (o `_call_with_retry` já trata o dele, mas nada impede que suba um), a
  mensagem dirá "o provedor não respondeu dentro de 60s" mesmo tendo passado um
  segundo. Diagnóstico ruim num caso raro; comparar o relógio antes de decidir
  resolveria.
- **`app/chat.py:227` — o ramo "condensação devolveu string vazia → fallback"
  segue sem teste.** Repetida da tentativa 1; uma linha no `FakeChatClient`
  (`condensed=""`) cobre.
- **Sugestões da tentativa 1 acatadas, conferidas por mim:** NFR-1, AC-23, §4.2
  e §4.8 da spec passaram a cobrar a **intenção** (mínimo de raciocínio) em vez
  do valor que o provedor recusa, e `.codeflow/manifest.md:17` deixou de
  anunciar `gemini-2.5-flash`. A nota de revisão 4 no cabeçalho da spec registra
  as três descobertas com a fonte. Bem feito.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh \
       .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
✓ §5 estruturalmente válida
EXIT=0
```

**I-1 da tentativa 1 — o `range` agora contém os commits que faltavam:**

```text
$ for s in 8a1c5f0 3c89162 85da080 f1f8be7 c64104f; do
      git merge-base --is-ancestor $s e2b7825 && echo "$s dentro de e2b7825"; done
8a1c5f0 dentro de e2b7825
3c89162 dentro de e2b7825
85da080 dentro de e2b7825
f1f8be7 dentro de e2b7825
c64104f dentro de e2b7825
$ git merge-base --is-ancestor e2b7825 HEAD && echo "ancestral de HEAD OK"
ancestral de HEAD OK
```

**Gates, rodados por mim na ponta da branch:**

```text
$ make check
cd backend && uv run ruff check .    → All checks passed!
cd backend && uv run mypy app        → Success: no issues found in 23 source files
Camadas: main -> api -> (chat | ingestion) -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Contracts: 4 kept, 0 broken.
262 passed, 19 deselected in 11.28s
Test Files  10 passed (10) | Tests  84 passed (84)
[exited with code 0]

$ make security                      → SEC=0, nenhuma vulnerabilidade
$ cd backend && uv run pytest -m db -q   → 19 passed, 262 deselected
```

**I-2 — a variável passou a ter consumidor:**

```text
$ grep -rn "chat_timeout_seconds" --include=*.py backend/
backend/app/config.py:47:    chat_timeout_seconds: int = 60
backend/app/adapters/gemini.py:458:  deadline = ... + self._settings.chat_timeout_seconds
backend/app/adapters/gemini.py:493:  f"o provedor não respondeu dentro de {...}s"
backend/tests/test_gemini_adapter.py:545:  chat_timeout_seconds=timeout,
```

**I-3 — cobertura do adapter, medida por mim:**

```text
Name                         Stmts   Miss Branch BrPart  Cover   Missing
app/adapters/gemini.py         200      3     36      4    97%   366, 384, 476->exit, 568
app/chat.py                    139      4     28      2    96%   227, 384-386, 397->exit
app/api/conversations.py        72     10     16      2    82%   56-59, 64-67, 140, 156
```

As três linhas que restam em `gemini.py` são do cliente de **embeddings**
(366, 384, pré-existentes) e a criação preguiçosa do cliente de chat (568). O
que a avaliação anterior apontou — `_thinking_config` nos dois ramos, caminho
feliz de `generate`, retry transitório, desistência em status não-retentável,
`chunk.text` nulo — está coberto, e conferi que as asserções são sobre o que
chegou ao transporte, não sobre a função privada:

```text
tests/test_gemini_adapter.py: assert thinking.thinking_level == types.ThinkingLevel.MINIMAL
                              assert thinking.thinking_budget is None
                              assert thinking.thinking_budget == 128
                              assert thinking.thinking_level is None
```

**Verificação do prazo (o achado I-1 novo), com o dublê da própria suíte:**

```text
(a) timeout=0 -> ChatProviderError | generate_content_stream chamado? False | closed=False
(b) timeout=1 -> ChatProviderError apos 1.00s | generate_content_stream chamado? True | closed=True

$ grep -n "stall" tests/test_gemini_adapter.py
472,480,508  (definição do dublê)
663          (único teste que usa: test_provedor_que_emudece_estoura_o_prazo_do_turno)
```

**Não re-executado por mim:** a revalidação pelo `docker compose` com a API real
(primeiro evento em 1,39 s, citação da página 2, recusa em 0,625). Continua não
existindo `.env` nesta árvore, e a medição gasta quota do owner. Corroboração
indireta: os dois documentos que o gate ingeriu estão no banco
(`Exemplo-YAITEC.pdf`, `session_id: gate-1787009836`, 10 chunks, `ready`), com
`created_at` coerente com o horário dos commits do rework.

## 7. Itens da fase / DoD não atendidos

- **Nenhum item da §5 em aberto.** Os nove `Passos`, os nove `Testes` e o
  critério de conclusão estão cobertos — os testes de integração pela `A.6`, os
  de unidade do adapter agora aqui.
- **Pendência de qualidade de teste, não de escopo:** o `Passo 1` da fase manda
  filtrar `chunk.text` nulo e passar o mínimo de raciocínio; ambos agora têm
  teste. O prazo do turno tem teste, mas do lado errado da fronteira (§4).

## 8. Divergências entre o relatório e o código real

- **Nenhuma divergência de fato.** As três correções descritas no §8 do
  `EXECUCAO` existem, nos commits que ele nomeia, e fazem o que ele diz.
- **Uma afirmação mais forte do que a evidência sustenta:** a tabela do §8 lista
  `test_provedor_que_emudece_estoura_o_prazo_do_turno` como o teste da lacuna
  "prazo do turno (I-2)". O teste existe e passa, mas não exercita o trecho que
  a correção do I-2 acrescentou (§4). É a mesma forma de otimismo que apontei na
  tentativa 1 sobre o `EXPLAIN` de 2.000 chunks — e que a `A.3`, nesta mesma
  rodada, evitou colando o teste vermelho antes da correção.

**Nota de perímetro:** o `HEAD` da branch (`e76fbed`) é posterior a este `range`
e alterou `backend/app/chat.py` (`_is_retry`, +27 linhas) e
`backend/tests/test_chat_api.py` dentro de um rework do **Track B**. Auditei a
mudança: ela preserva FR-9 (a pergunta continua persistida antes da chamada ao
provedor; no retry ela já está lá) e não contradiz nada desta fase. Fica
registrado porque repete, do lado do Track B, exatamente o padrão que o I-1 da
`A.6` fechou do lado do Track A — e porque significa que este `range` já não
descreve o `app/chat.py` de HEAD.
