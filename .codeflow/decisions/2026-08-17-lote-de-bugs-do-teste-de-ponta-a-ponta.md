---
versão: 1.0
status: estável
atualizado: 2026-08-17
data: 2026-08-17
workflow: batch-bugfix
tags: [rag, retrieval, prompt, ui, entrega]
status_decisão: ativa
supersede: null
relaciona-com: [2026-08-17-revisao-adversarial-das-specs]
---

# Decisão: correções do lote `feat-0002-teste-ponta-a-ponta`

## Contexto

O teste de ponta a ponta do owner, feito antes da fase `B.5`, encontrou cinco
defeitos que os gates verdes não pegaram. Três deles têm a mesma raiz de método:
**a suíte e o eval mediam o sistema com as entradas que os autores imaginaram,
não com as que uma pessoa digita.** O lote inteiro está no ledger
`.codeflow/bug-batches/feat-0002-teste-ponta-a-ponta.md`.

Esta decision registra as escolhas não-triviais; o que foi só troca de texto
está no ledger e não precisa de registro próprio.

## Decisões

### 1. Limiar de similaridade: 0,625 → 0,561, com o dataset ampliado antes (BUG-002)

O limiar não foi movido "para deixar de recusar". O dataset ganhou **sete
positivas sem o nome da empresa** (P11–P16 e C03), escritas a partir do texto
extraído antes de qualquer medição, e o corte foi recalculado pelo mesmo método
da `A.5`: o meio da folga entre a negativa mais alta e a positiva mais baixa.

| | antes | depois |
|---|---|---|
| positiva mais baixa | 0,724 | 0,596 |
| negativa mais alta | 0,526 | 0,526 |
| folga | 0,198 | 0,070 |
| limiar | 0,625 | **0,561** |
| falsa recusa | 0,000 | 0,000 (era 0,105 com 0,625) |

**Por que não bastava baixar a constante:** trocar o número sem dado novo é
exatamente o que a `A.5` existe para impedir. E o dado novo mostrou que a folga
de 0,198 media a distância entre negativas fora do assunto e positivas com
âncora — dois grupos que o uso real não produz.

**O caminho arquitetural não foi acionado.** O relato do BUG-002 previa que, se
os grupos passassem a se sobrepor, o limiar sozinho deixaria de servir e entraria
reranking ou uma segunda condição de recusa. Não aconteceu: a folga encolheu, mas
não sumiu. Fica registrado que a margem caiu de ~0,10 para ~0,035 de cada lado —
é menos confortável, e o que compraria margem de volta é aumentar a separação
(reranking, ou a query lexical menos restritiva que a `A.7` já deixou apontada),
não mexer no corte de novo. Medição completa em `backend/eval/README.md`.

### 2. FR-8 passa a descrever o que o código faz: chunks consultados (BUG-003)

FR-8 dizia "dos chunks **usados**"; o pipeline emite os que passaram do limiar,
que é um conjunto maior. O owner escolheu, entre os três caminhos do relato, o
**(1): renomear na interface e corrigir a spec**.

- **Descartado o (2)** — pedir ao modelo os índices usados e filtrar por eles:
  cria um caminho novo de falha (modelo que não obedece → resposta sem citação
  nenhuma) e colide de frente com o BUG-005, que manda o modelo **não** falar de
  trechos numerados.
- **Descartado o (3)** — baixar `RETRIEVAL_TOP_K` de 5 para 3: não resolve o
  problema conceitual e mexe na mesma medição que o BUG-002 acabou de recalibrar.

O débito que fica aberto: a interface passou a dizer a verdade ("trechos
consultados"), mas **o produto continua sem saber quais trechos a resposta usou**.
Se isso virar requisito, o caminho é o (2), e ele exige um contrato de saída do
modelo — não um ajuste de rótulo.

### 3. Heurística de condensação: `< 5` palavras e formas contraídas (BUG-001)

O limiar de palavras subiu de 4 para 5 e as contrações (`dele`, `dela`, `nele`,
`nela`, `disso`, `nisso`, `desse`, `dessa` e plurais) entraram na lista de
marcadores. 5 é o **teto** admissível: o AC-3 exige que "qual o endereço da
empresa?", de cinco palavras, não seja condensada.

O que isso custa: perguntas de 4 palavras passam a gastar uma chamada de
condensação que antes não gastavam, num teto de ~10 RPM. É o preço de não
recusar uma pergunta que o documento responde — e a recusa falsa é o modo de
falha mais caro deste produto.

FR-3 e o §5 da spec foram corrigidos junto (revisão 5), para que código e texto
não divirjam de novo.

### 4. Mensagem de quota deixa de prometer um minuto (BUG-004)

O `429` do plano gratuito pode ser a cota por minuto **ou** a de 20 requisições
por dia por modelo, e o adapter não distingue as duas. Em vez de inventar a
distinção — lógica nova para ler o `quotaId` do corpo do erro —, os dois textos
passaram a cobrir os dois casos. Registrado o que ficou de fora: distinguir a
cota é possível e barato, mas é código novo numa entrega que não precisa dele.

### 5. Edição autorizada do `.env` local

A constitution universal proíbe modificar `.env` sem instrução explícita. O owner
autorizou explicitamente a alteração de **uma** linha —
`SIMILARITY_THRESHOLD=0.625` → `0.561` — para que a verificação de ponta a ponta
rodasse contra o valor recalibrado. Nenhuma outra linha foi tocada. Registrado
porque uma proibição da constitution só cede com autorização explícita, e essa
autorização precisa ficar por escrito.

## Consequências

- `make check` verde (277 testes de backend, 86 de frontend), `make eval` com
  gate NFR-7 atingido em `0.561`.
- Os quatro sintomas do relato foram reproduzidos contra a API real depois do fix
  e voltaram corretos — inclusive `top_score` de 0,527 → 0,796 na continuação de
  quatro palavras.
- Fica em aberto, para quem for medir depois: a margem de 0,035 do limiar, e a
  ausência de correspondência entre trecho citado e trecho usado.
