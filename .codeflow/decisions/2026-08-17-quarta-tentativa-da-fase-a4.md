---
versão: 1.0
status: estável
atualizado: 2026-08-17
data: 2026-08-17
workflow: execute-spec-phase
tags: [processo, execucao, gates, testes]
status_decisão: ativa
supersede: null
relaciona-com: [2026-08-17-paralelizacao-de-tracks-sem-gate-fechado]
---

# Decisão: autorizar uma quarta tentativa da fase `A.4`, restrita a uma constante

## Contexto

A fase `A.4 chat-endpoint` acumulou **três vereditos não-APROVADO** em avaliações
independentes:

| Tentativa | Veredito | Achados |
|---|---|---|
| 1 | RESSALVAS | range descrevia código já corrigido; `CHAT_TIMEOUT_SECONDS` morto; adapter sem teste de unidade |
| 2 | RESSALVAS | o teste do prazo escrito na tentativa 2 não exercitava o laço que dizia proteger |
| 3 | RESSALVAS | o teste que fechou o achado anterior é intermitente |

`ARTIFACTS_SPEC` §2.11.4 define o teto: **três vereditos não-APROVADO param a
fase**, e a próxima seleção de rework escala ao owner. O estado terminal previsto
é decisão humana, não outro ciclo executor↔avaliador. A constitution universal
reforça: gate duro não admite override conversacional, e um override genuíno
exige decision arquitetural registrada **antes** da próxima invocação. Este
registro é essa decision, e ela existe antes do rework que autoriza.

## O que a investigação apurou antes da decisão

O terceiro achado — `assert models.closed is True` falhando ~1 em 15 execuções —
deixou uma dúvida que o avaliador declarou não conseguir separar:

1. corrida na asserção → defeito só do teste;
2. `aclose()` não finaliza o iterador no cancelamento → defeito de produção, com
   FR-12 não cumprido justamente quando o prazo estoura.

A investigação rodou **fora do repositório**, por um plugin de pytest que
instrumenta o dublê, e fechou a dúvida:

- **Em toda falha, o corpo do gerador nunca executou** (`iniciou: False`,
  `closed: False`), com correlação perfeita em 12 rodadas. Com o orçamento de
  50 ms já consumido antes da primeira leitura, `wait_for` cancela sem iniciar o
  gerador — e um gerador que não começou não tem `finally` para rodar. `aclose()`
  nele é no-op **correto**.
- **Em 400 rodadas em que o corpo iniciou, `closed` foi `True` 400 vezes.** A
  hipótese 2 está descartada por medição: **FR-12 está cumprido**.
- A falha é reproduzível sob demanda: **17 em 30** com CPU carregada, **0 em 40**
  ociosa.
- O remédio sugerido pela avaliação (`await asyncio.sleep(0)` antes da asserção)
  **não resolveria**: não há nada pendente quando o corpo nunca entrou. Ele teria
  devolvido "não estabilizou" e migrado o achado para `gemini.py` por engano.

Correção validada sob a mesma carga que produz as falhas:

| prazo no teste | falhas em 25, com CPU carregada |
|---|---|
| 0,05 s (atual) | 17 |
| 0,5 s | 0 |

## Decisões tomadas

1. **O owner autoriza uma quarta tentativa da `A.4`**, sabendo que ela passa do
   teto de §2.11.4. A alternativa considerada e rejeitada foi aceitar a fase com
   o achado como dívida no README: o custo real seria um `make check`
   intermitentemente vermelho na frente de quem avalia o desafio, que é o pior
   cenário possível de uma entrega que se vende por "roda de primeira".

2. **O escopo do rework é uma constante**: o orçamento do teste
   `test_provedor_que_emudece_no_meio_do_stream_estoura_o_prazo_do_turno` passa
   de `0.05` para `0.5` segundo. Nenhuma linha de produção muda — a investigação
   provou que não há o que corrigir lá. Qualquer achado novo fora dessa linha
   **não** é coberto por esta autorização e volta a parar a fase.

3. **O teto continua valendo para as demais fases** e para a própria `A.4` daqui
   em diante. Esta decisão não revisa a regra: ela registra uma exceção nomeada,
   com escopo fechado e justificativa medida. Se a `A.4` voltar não-APROVADO
   outra vez, a fase para de novo e exige nova decisão.

4. **A asserção não é enfraquecida.** `pytest.mark.flaky`, rerun automático ou
   remover o `assert models.closed` foram rejeitados: trocariam a evidência de
   FR-12 por silêncio — a mesma troca que o `CHAT_TIMEOUT_SECONDS` morto
   representava, e que a tentativa 2 corrigiu.

## Consequências

- A `A.4` é reemitida como `tentativa: 4`, `reprovacoes: 3`, com `sha_inicial`
  preservado.
- O teste passa a custar ~0,5 s numa suíte de ~12 s.
- Fica registrado que um orçamento de prazo em teste precisa ser folgado em
  relação ao jitter da máquina, e não apertado para o teste terminar rápido: é a
  segunda vez nesta spec que uma constante de tempo em teste produz achado.
