---
spec: 02-chat-rag
fase: A.4
slug_fase: chat-endpoint
tentativa: 3
veredito: RESSALVAS
score: 9.8
threshold: 8.5
range_avaliado: 7fe47de9ac92e62523d38eab7366615b7d70d0bb..defa164b815295c39781376b2fc10fa7f6630b48
---

# FASE A.4 — Avaliação independente (tentativa 3)

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 9.8 / threshold 8.5

**Leia o §4 antes de decidir qualquer coisa: este é o terceiro veredito
não-APROVADO da fase.** Com `reprovacoes: 2` no relatório desta tentativa, o teto
de §2.11.4 fecha aqui — a próxima seleção de rework **para e escala ao owner**.
Não recomendo mais um ciclo cego; recomendo a decisão humana descrita no §5.

**O achado da tentativa 2 está fechado, e fechado bem.** Provei o teste mordendo,
três rodadas de cada lado, removendo apenas a linha protegida:

```
codigo atual         -> PASSOU  em 0.05s   (×3)
sem prazo no laco    -> FALHOU  em 5.01s   (×3, TimeoutError da guarda)
```

O `wait_for` externo de 5 s foi um acerto que a minha sugestão não previa: sem
ele, a ausência do prazo penduraria a suíte em vez de reprová-la. As três
sugestões abertas também fecharam, e verifiquei que a fixture da `A.3`
**continua mordendo** depois de largar o `ALTER ROLE` (§6).

**O que segura o APROVADO é um achado novo e estreito:** o teste que fecha o
achado anterior é **flaky**. A asserção `models.closed is True`
(`test_gemini_adapter.py:682`) falha em cerca de **1 a cada 15 execuções** —
observei três falhas em 16 invocações do pytest e uma no meu próprio arranjo.
Como esse teste está dentro do `make test`, o gate `make check` do projeto passou
a ter uma chance real de sair vermelho sem nenhuma mudança de código.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | O achado da t2 está fechado com prova de mordida (§6); escopo travado intacto — nenhuma chamada ao Gemini fora do adapter, sem buffer, sem `GZipMiddleware`, `embed_query` reusado, nada de prompt ou pergunta em `info` |
| 2 | Arquitetura e direção de dependências | 3 | 5 | O prazo segue no adapter, sem tocar o protocolo `ChatClient` de §4.2; `Contracts: 4 kept, 0 broken` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | Mensagem do estouro sem prompt e sem chave; `make security` exit 0, sem vulnerabilidade |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `_with_deadline` reusa `_fail_chat` e a classificação de status já existente; o teste irmão reusa o mesmo dublê |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `chat_timeout_seconds`/`condense_timeout_seconds` viraram `float` (`config.py:50-51`) com a razão registrada — é o tipo que `asyncio.wait_for` recebe; `.env.example:46-54` explica os dois prazos, incluindo por que o da condensação é curto |
| 6 | Local e nomes dos arquivos | 2 | 5 | `config.py`, `.env.example` e três arquivos de teste; nenhum arquivo de produção tocado nesta tentativa |
| 7 | Qualidade de código | 2 | 5 | `GUARDA_SEGUNDOS` como constante nomeada e explicada (`test_gemini_adapter.py:52`); o comentário obsoleto de `test_chat_api.py` foi reescrito e o laço de polling virou asserção direta |
| 8 | Testes e cobertura | 2 | 4 | O teste do prazo agora morde, provado nos dois estados; um teste irmão trava a outra metade; a fixture da `A.3` perdeu o estado global sem perder a mordida. Desconta: o teste do prazo é flaky (§4) |

Score = (5·3 + 5·3 + 5·3 + 5·3 + 5·2 + 5·2 + 5·2 + 4·2) / 20 × 2 = **9.8**

O score subiu de 9,6 para 9,8 e ainda assim o veredito é RESSALVAS: as duas
coisas medem eixos diferentes, e um IMPORTANTE reprova qualquer que seja o score.
O trabalho desta tentativa é bom — o que resta é um defeito estreito num teste.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

### I-1 — `backend/tests/test_gemini_adapter.py:682` — o teste que fecha o achado anterior é flaky (~1 em 15) e pode avermelhar o `make check`

```python
    with pytest.raises(ChatProviderError):
        await asyncio.wait_for(coletar(build_chat_client(models, timeout=0.05)), GUARDA_SEGUNDOS)

    assert models.models_pedidos == ["modelo-de-teste"], "o stream nem chegou a ser aberto"
>   assert models.closed is True, "o iterador do provedor ficou aberto após o estouro"
E   AssertionError: o iterador do provedor ficou aberto após o estouro
E   assert False is True
```

**Medido, não suposto.** Quinze execuções isoladas do teste: **14 verdes, 1
vermelha**. Um laço novo depois disso falhou já na primeira rodada. Somando o
arranjo que escrevi para provar a mordida, são **três falhas observadas** — todas
na mesma asserção, todas com a mensagem acima.

```text
$ for i in $(seq 1 15); do uv run pytest ... -k "emudece"; done | sort | uniq -c
     14 1 passed, 44 deselected
      1 1 failed, 44 deselected
```

**Por que isto é IMPORTANTE e não sugestão.** A rule `testing` do framework é
categórica: *"Teste é determinístico. Flakiness é tratado como bug, não como
tolerância."* E o efeito prático é maior que o de um teste isolado: este teste
roda dentro de `make test`, que é o `make check` que a DoD da spec (§9) e a
constitution do projeto exigem em zero. Um avaliador do desafio que rode
`make check` uma vez tem chance não desprezível de ver a suíte vermelha, sem
nada errado no produto — que é o pior resultado possível para uma entrega.

**Duas hipóteses, e eu não consegui separá-las** — digo isso em vez de escolher a
mais conveniente:

1. **Corrida na asserção.** `asyncio.wait_for` cancela a task de `anext(stream)`;
   o `finally` de `FakeAsyncModels._emitir` (que marca `closed`) roda durante o
   desenrolar da cancelação, e a asserção às vezes chega antes de ele terminar.
   Neste caso o defeito é só do teste, e a correção é esperar o fechamento ou
   observá-lo por outro caminho.
2. **`aclose()` nem sempre finaliza o iterador nesse caminho.** Se for isto, o
   `finally` de `stream_answer` (`gemini.py:471-477`) não estaria cumprindo FR-12
   quando o prazo estoura, e o defeito seria de **produção**: a conexão com o
   provedor ficaria aberta exatamente no caso em que se quer fechá-la.

Tentei instrumentar o dublê para distinguir as duas, e o próprio instrumento
mudou o tempo o bastante para o problema sumir em 40 rodadas — o que é sintoma
de corrida, mas não é prova de que a hipótese 2 esteja descartada.

**Correção sugerida — nesta ordem:**

1. **Descobrir qual das duas é.** Um `await asyncio.sleep(0)` antes da asserção
   responde em uma linha: se o teste estabilizar, é a hipótese 1 e o produto está
   íntegro; se continuar falhando, é a hipótese 2 e o achado migra para
   `gemini.py`.
2. **Se for a hipótese 1**, trocar a asserção por uma espera explícita e curta
   (com prazo próprio, para não voltar a pendurar a suíte) — ou observar o
   fechamento pelo lado do adapter, que é onde ele é determinístico.
3. **Se for a hipótese 2**, o `finally` precisa garantir a finalização antes de
   deixar a exceção subir, e aí é código de produção, não teste.

**Não** recomendo `pytest.mark.flaky`, `rerun` ou remover a asserção: seria trocar
a evidência de FR-12 pelo silêncio, que é a mesma troca que o I-2 da tentativa 1
apontou na configuração morta.

## 5. Sugestões

- **O teto de tentativas fecha aqui — a decisão é do owner, não de outro rework.**
  `reprovacoes: 2` nesta tentativa; com este veredito, a fase acumula três
  não-APROVADOS e §2.11.4 manda **parar e escalar**. Concretamente, três saídas
  legítimas, todas do owner:
  1. **Aceitar a fase com o achado registrado** e tratar o I-1 como dívida
     conhecida, anotada no README junto das limitações — o produto está íntegro
     se a hipótese 1 se confirmar;
  2. **Autorizar um rework de exceção**, restrito ao passo 1 do I-1 (uma linha
     para descobrir qual hipótese é a certa), com o resultado decidindo o resto;
  3. **Registrar uma decision arquitetural** que revise o teto para esta fase,
     que é o único caminho de override que a constitution admite ("gates duros
     não admitem override conversacional").
  Recomendo a **(2)**: o custo é uma linha, e ela transforma uma incerteza sobre
  FR-12 em fato.
- **`test_gemini_adapter.py:615` — a outra asserção de `closed` é estável.** Ela
  está no caminho de conclusão normal (`test_stream_fecha_o_iterador_do_provedor_ao_terminar`),
  sem cancelação envolvida, e não falhou em nenhuma das minhas execuções. Fica
  registrado para o diagnóstico do I-1: o que distingue os dois casos é a
  cancelação, não o `aclose()`.
- **`test_retrieval.py:298-320` — `PoolFixo` com `# type: ignore[arg-type]`.** O
  shim é a forma certa de não acrescentar a `Database` um parâmetro que só o
  teste usaria, e o `mypy` do gate roda só sobre `app`. Registro só para que o
  `ignore` não seja lido depois como descuido: ele é deliberado e local.
- **Mantida das rodadas anteriores:** `app/chat.py:227` — o ramo "condensação
  devolveu string vazia → fallback" segue sem teste. Uma linha no
  `FakeChatClient` (`condensed=""`) cobre.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh \
       .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
EXIT=0

$ git merge-base --is-ancestor defa164 HEAD && echo "defa164 ancestral de HEAD OK"
defa164 ancestral de HEAD OK

$ make check
Contracts: 4 kept, 0 broken.
app/core/condensation.py      31      0     10      0   100%
app/core/models.py            40      0      0      0   100%
app/core/prompt.py            28      0      6      0   100%
app/core/retrieval.py         21      0      4      0   100%
Required test coverage of 90% reached. Total coverage: 99.55%
263 passed, 19 deselected in 13.72s
Test Files  10 passed (10) | Tests  84 passed (84)
[exited with code 0]

$ make security
bandit -q -r app             → (sem saída)
pip-audit                    → No known vulnerabilities found
npm audit --audit-level=high → found 0 vulnerabilities
SEC=0

$ cd backend && uv run pytest -m db -q
19 passed, 263 deselected in 2.07s
```

**Prova de que o teste do prazo agora morde** — substituí `stream_answer` por uma
cópia sem o `_with_deadline` de dentro do laço (só na memória do meu processo, o
repositório não foi tocado) e rodei o corpo do teste três vezes de cada lado:

```text
[0] codigo atual         -> PASSOU em 0.05s
[1] codigo atual         -> PASSOU em 0.05s
[2] codigo atual         -> PASSOU em 0.05s
[0] sem prazo no laco    -> FALHOU (TimeoutError da guarda de 5s) em 5.01s
[1] sem prazo no laco    -> FALHOU (TimeoutError da guarda de 5s) em 5.00s
[2] sem prazo no laco    -> FALHOU (TimeoutError da guarda de 5s) em 5.01s
```

A guarda externa funciona como anunciado: sem o prazo, o modo de falha é vermelho
em cinco segundos, e não uma suíte pendurada.

**Prova do achado I-1 (flakiness):**

```text
$ for i in $(seq 1 15); do uv run pytest tests/test_gemini_adapter.py -k "emudece" -q; done \
      | sed 's/in .*s$//' | sort | uniq -c
     14 1 passed, 44 deselected
      1 1 failed, 44 deselected

# saída da rodada vermelha
>       assert models.closed is True, "o iterador do provedor ficou aberto após o estouro"
E       AssertionError: o iterador do provedor ficou aberto após o estouro
E       assert False is True
tests/test_gemini_adapter.py:682: AssertionError
```

**Sugestão da `A.3` fechada sem perder a mordida** — desliguei a correção do I-1
da `A.3` por um plugin de pytest (sem tocar o repositório) e rodei os testes `db`
com a fixture nova, baseada em `server_settings`:

```text
# com a correção
6 passed, 17 deselected in 0.92s

# com `hnsw.iterative_scan = off` injetado
>       assert len(recuperados) == 5
E       assert 0 == 5
E        +  where 0 = len([])
1 failed, 5 passed, 17 deselected in 0.76s
```

**Nenhum estado global sobrou no banco** (era o ponto da sugestão):

```text
$ SELECT rolconfig FROM pg_roles WHERE rolname='talkdoc'   → None
enable_seqscan: on | hnsw.ef_search: 40 | hnsw.iterative_scan: off
documentos: 2 | chunks: 18   (os mesmos de antes da avaliação)
```

**Prazos consumidos e documentados:**

```text
$ grep -n "chat_timeout_seconds\|condense_timeout_seconds" backend/app/config.py
50:    chat_timeout_seconds: float = 60.0
51:    condense_timeout_seconds: float = 5.0
$ .env.example:46-54 — os dois prazos com explicação do porquê de cada um
```

**Não re-executado por mim:** a revalidação pelo `docker compose` com a API real.
O `.env` da árvore principal agora existe (criado por outra sessão) e aponta para
`gemini-3.1-flash-lite`, diferente do default do código; subir o compose gastaria
quota do owner e mediria um modelo que não é o do `.env.example`. Fica como `[—]`
justificado.

## 7. Itens da fase / DoD não atendidos

- **DoD global "`make check` retorna zero, offline"** — atendido nas minhas
  execuções, **mas não garantido**: o I-1 introduz uma chance de ~7% de a suíte
  sair vermelha sem mudança de código. É o único item da §9 com ressalva.
- Todos os `Passos` (1–9), os nove `Testes` da fase e o critério de conclusão
  seguem atendidos; o range contém o defeito de FR-11 e a sua cura.

## 8. Divergências entre o relatório e o código real

- **Nenhuma.** As quatro afirmações do §8 do `EXECUCAO` — teste com
  `timeout=0.05`, as duas asserções novas, o `wait_for` de guarda e o teste irmão
  — existem no código e fazem o que ele diz. A prova de mordida que o relatório
  cola bate com a que eu produzi por outro caminho.
- **Uma coisa que o relatório não podia saber:** ele afirma "1 failed …
  TimeoutError em 5,10 s; com ela, 2 passed em 0,12 s", o que é verdade — mas uma
  única execução verde não revela a flakiness. Foram precisas quinze para ela
  aparecer. Não é divergência; é o limite de uma amostra de tamanho um, e vale
  como nota de método para as próximas provas de mordida.

**Nota de perímetro (fora da responsabilidade desta fase):** a árvore de trabalho
tem alterações **não commitadas** de outra sessão nos quatro
`FASE-B.*-EXECUCAO.md` e um diretório `artefatos/gate-b/` não rastreado. Não
toquei em nada disso, e a minha avaliação rodou contra o `HEAD` commitado. Junto
com o `app/chat.py` alterado pelo Track B na rodada anterior e com o banco do
compose disputado entre as duas sessões, é o terceiro sintoma do mesmo problema —
o que a decision `2026-08-17-paralelizacao-de-tracks-sem-gate-fechado.md` já
registra e o que a `A.6` fechou do lado do Track A.
