---
versão: 1.0
status: estável
atualizado: 2026-08-18
data: 2026-08-18
workflow: batch-bugfix
tags: [ui, ingestao, chat, observabilidade, configuracao, entrega]
status_decisão: ativa
supersede: null
relaciona-com: [BUG-006, BUG-007, BUG-008, BUG-009, BUG-010]
---

# Decisão: correções da segunda rodada do teste de ponta a ponta

## Contexto

A segunda rodada automatizada encontrou cinco defeitos que não comprometiam a
indexação nem a persistência, mas pioravam a demonstração, a mensagem de erro e
a rastreabilidade dos turnos. O ledger do lote está em
`.codeflow/bug-batches/segunda-rodada-teste-ponta-a-ponta.md`.

## Decisões

### 1. A casca da aplicação ocupa a viewport (BUG-006)

`AppShell` passa a usar `h-dvh`. Isso dá altura definida à linha central do
grid, para que o `h-full` do chat mantenha a lista rolável e o campo de pergunta
visível. Não foi restaurado o antigo `calc(100dvh - 14rem)`: ele duplicava uma
medida que pertence à casca e voltaria a desalinhar quando ela mudasse.

### 2. Validação de entrada e PDF inválido são códigos diferentes (BUG-007)

`arquivo_invalido` fica restrito a um conteúdo que não é PDF. A validação genérica
do FastAPI usa o novo `entrada_invalida`, com uma mensagem de interface sobre o
limite de 2.000 caracteres. Isso preserva o envelope e o mapeamento por código,
mas deixa a ação sugerida coerente com a tela de chat.

### 3. Ingestões rápidas ganham avanço estimado e identificado (BUG-008)

Enquanto um documento que cabe no lote padrão conhece o total de chunks mas
ainda confirma zero processados, a barra avança suavemente por uma estimativa
assintótica e mostra “Preparando a leitura…”. Documentos de vários lotes ficam
estritamente na porcentagem confirmada pelo servidor. Não foram reduzidos os
lotes de embedding: mais chamadas para o provedor só para animar o PDF de
demonstração pioraria a ingestão maior.

### 4. O fallback da condensação espera no máximo 2 s (BUG-009)

O timeout cai de 5 s para 2 s. A condensação continua ocorrendo sempre que há
histórico; nenhuma heurística baseada no tamanho da pergunta foi reintroduzida,
pois ela reabriria o BUG-001. Se o provedor atrasar, a busca segue com o fallback
já existente após 2 s.

### 5. O fechamento do stream fecha os dois geradores (BUG-010)

`stream_turn` fecha explicitamente o gerador interno de resposta ao ser
cancelado. O evento `chat.generated` é emitido no `finally` antes das operações
assíncronas de limpeza, para que um turno interrompido ainda tenha um fecho com
`truncated: true` no log.

## Consequências

- `make check` verde: 280 testes backend, 118 frontend e cobertura de core em
  99,58%.
- BUG-006 permanece com reprodução manual de navegador como prova de layout:
  jsdom não calcula a altura/rolagem reais; o teste de componente garante a
  altura definida que torna essa reprodução possível.
- O lote está pronto para `/double-check`.
