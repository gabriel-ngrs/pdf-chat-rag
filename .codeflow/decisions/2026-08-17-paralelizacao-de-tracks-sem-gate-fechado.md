---
versão: 1.0
status: estável
atualizado: 2026-08-17
data: 2026-08-17
workflow: execute-spec-phase
tags: [processo, execucao, gates, entrega]
status_decisão: ativa
supersede: null
relaciona-com: [2026-08-17-revisao-adversarial-das-specs]
---

# Decisão: paralelizar os tracks da FEAT-0002 com o gate da `A.4` ainda aberto

## Contexto

A `FEAT-0002` tem dois tracks. O Track B (`B.1` a `B.4`, interface do chat)
declara `Depende de: A.4` — o endpoint de chat com streaming. As quatro fases do
Track B foram executadas num worktree paralelo **antes** de a `A.4` existir, por
instrução verbal, para caber no orçamento de horas do desafio.

`ARTIFACTS_SPEC` §2.11.4 trata dependência declarada como gate duro: só fase
`APROVADO` libera as dependentes, e um override precisa de decision arquitetural
registrada **antes** da invocação. Não havia nenhuma — este registro é
retroativo, e é o próprio défice que ele documenta.

O custo apareceu na avaliação independente das quatro fases (artefatos
`FASE-B.{1,2,3,4}-*-AVALIACAO.md`): as quatro reprovaram, todas pelo mesmo
motivo — o critério de conclusão de cada uma exige o backend no ar, e nenhum
pôde ser cumprido. Nenhuma reprovou por código: os scores ficaram entre 8,6 e
9,4, e a auditoria do contrato cliente↔servidor feita depois, com a `A.4` já na
`dev`, casou campo a campo.

## Decisões tomadas

### 1. Registrar a paralelização como override consciente, não como precedente

**Por quê:** o ganho existiu e é mensurável — o Track B saiu com quatro fases
implementadas, testadas offline e com contrato correto contra um servidor que
ainda não existia. O custo também é mensurável: quatro fases `REPROVADO`, quatro
gates a executar de uma vez e uma rodada extra de avaliação. Registrar os dois
lados é o que impede a próxima paralelização de ser decidida pela lembrança de
que "deu certo".

**Alternativa rejeitada:** executar os tracks em série. Rejeitada no momento em
que a decisão foi tomada — o orçamento de horas não fechava —, e não se pretende
reavaliá-la retroativamente.

**Implicações:** os quatro gates da §5 do Track B são executados numa única
passada contra o `docker compose`, com a `A.4` na `dev`; cada fase registra a
evidência na sua tentativa 2 e volta para avaliação em chat zerado.

### 2. Paralelizar só quando o contrato entre os tracks estiver fechado na spec

**Por quê:** o que fez o código do Track B sobreviver à ausência do servidor não
foi sorte: a §4.3 (protocolo SSE) e a §4.4 (contrato de API) já estavam fixadas
como fonte única antes de qualquer fase rodar, e o cliente foi escrito contra
elas. Sem esse contrato congelado, paralelizar produz retrabalho de código, não
só de gate.

**Alternativa rejeitada:** paralelizar por conveniência de agenda, resolvendo o
contrato na integração. Rejeitada porque é exatamente o Risco 5 da spec
("contrato SSE divergir entre tracks").

**Implicações:** a condição para repetir a paralelização é objetiva — contrato de
borda fechado na spec — e é verificável antes de invocar as fases.

### 3. Fase que roda com dependência aberta declara o gate como pendente, nunca como cumprido

**Por quê:** foi o que o executor fez, e é o comportamento certo: nada foi
simulado contra stub, nenhum item foi dado por cumprido. O que a decisão fixa é
que isso não é zelo opcional — é a condição que mantém a paralelização
recuperável. Gate cumprido contra dublê teria escondido os quatro bloqueios e
levado o defeito para a demonstração.

**Implicações:** `status: executado` com gate aberto não conclui a fase e não
libera as dependentes; só `APROVADO` conclui.
