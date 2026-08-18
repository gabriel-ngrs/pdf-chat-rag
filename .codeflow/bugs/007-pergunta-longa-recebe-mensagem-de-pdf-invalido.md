---
id: BUG-007
titulo: "Pergunta acima de 2.000 caracteres volta como 'Arquivo não é um PDF válido'"
descoberto_em: 2026-08-18
descoberto_por: segunda rodada do roteiro de ponta a ponta, automatizada com Playwright (bloco 6)
severidade: média
fase_dona: A.1 (foundation, dona de `errors.py`) — com efeito na B.2 (`lib/errors.ts`)
status: aberto
---

# BUG-007 — A recusa de pergunta longa fala de arquivo

## Sintoma

Colar um texto de 3.000 caracteres no campo de pergunta e enviar. O servidor
recusa — corretamente, o teto é 2.000 — e a tela mostra:

> **Arquivo não é um PDF válido**
> O conteúdo enviado não abre como PDF. Confira se o arquivo abre no seu leitor
> e envie de novo.

A pessoa colou **texto numa pergunta** e recebeu instruções sobre **abrir um
arquivo**. Não há arquivo nenhum envolvido nessa interação: a tela de upload
ficou para trás, e o que está aberto é a conversa.

Nada quebra: a pergunta continua no campo, a conversa não ganha balão órfão,
não vaza detalhe técnico. O defeito é inteiro na mensagem, e ela manda para o
lugar errado — quem seguir a instrução vai conferir um PDF que está perfeito.

## Causa raiz

Duas metades, cada uma correta sozinha.

**No servidor**, o teto da pergunta é validado pelo Pydantic
(`api/schemas.py:76-79`), o que produz um `422` do próprio framework. A tabela
que traduz status HTTP em código de domínio (`errors.py:120-124`) mapeia:

```python
_HTTP_ERROR_CODES = {
    404: NotFoundError.code,
    413: FileTooLargeError.code,
    422: InvalidFileError.code,   # <-- aqui
    429: RateLimitError.code,
}
```

A resposta sai assim, e a mensagem do servidor até é neutra:

```json
{"code":"arquivo_invalido","message":"Os dados enviados são inválidos. Confira o formulário e tente de novo."}
```

**No cliente**, `lib/errors.ts` traduz por `code`, nunca por mensagem — que é a
decisão certa e está documentada no cabeçalho do arquivo. Só que
`arquivo_invalido` está descrito como problema de PDF, porque quando o mapa foi
escrito era o único jeito de aquele código aparecer:

```ts
arquivo_invalido: {
  title: 'Arquivo não é um PDF válido',
  message: 'O conteúdo enviado não abre como PDF.',
  action: 'Confira se o arquivo abre no seu leitor e envie de novo.',
}
```

O `422` nasceu do upload e herdou o vocabulário do upload. Quando o chat passou
a ter validação de corpo, passou a emitir o mesmo código para um problema de
outra natureza — e o texto do cliente, que é fiel ao código, ficou fiel à coisa
errada.

## Reprodução

```bash
python3 - <<'EOF'
import json, urllib.request
q = 'A YAITEC é uma empresa. ' * 130          # 3.120 caracteres
body = json.dumps({'question': q}).encode()
req = urllib.request.Request(
    'http://localhost:8000/api/conversations/<id>/messages',
    data=body, headers={'content-type': 'application/json'})
try:
    urllib.request.urlopen(req)
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode())
EOF
# 422 {"code":"arquivo_invalido","message":"Os dados enviados são inválidos..."}
```

Pela interface: abrir a conversa, colar 3.000 caracteres, `Enter`.

## Correção sugerida

Um código próprio para "a entrada não passa na validação", separado do código
que fala de arquivo. Toca as duas pontas, e é pequeno nas duas:

1. **`errors.py`** — uma classe `InvalidInputError` com `code =
   "entrada_invalida"` e `status_code = 422`, e o mapa passa a apontar
   `422 → InvalidInputError.code`. O `arquivo_invalido` continua existindo,
   levantado explicitamente por `documents.py` quando o corpo não é PDF — que é
   o único lugar onde ele descreve a verdade.
2. **`lib/errors.ts`** — mais uma entrada em `DESCRIPTIONS` e em `ERROR_CODES`.
   Algo como *"A pergunta é longa demais / O servidor aceita até 2.000
   caracteres. Encurte a pergunta e envie de novo."*

Vale conferir se o teto ainda faz sentido em 2.000 (`MAX_QUESTION_LENGTH`), mas
isso é outra conversa: o defeito aqui é a mensagem, não o limite.

**Não** resolver colocando `maxlength` no `textarea`. Cortar a digitação em
silêncio esconde o limite em vez de explicá-lo, e o servidor continua sendo a
fronteira de confiança — a mensagem precisa estar certa de qualquer forma.

## Teste de regressão

Backend: `tests/test_errors.py` já cobre a tabela de status; acrescentar que
`422` produz `entrada_invalida` e que `arquivo_invalido` continua saindo do
upload não-PDF. Frontend: `lib/errors.test.ts` já verifica que todo código de
`ERROR_CODES` tem descrição — o código novo entra nessa varredura sozinho.

## Encaminhamento

`/bugfix`. Dona de `errors.py` é a `A.1` (foundation) da `01-ingestao-pdf`;
`lib/errors.ts` foi escrito na `B.2` e ampliado na `B.4` da `02-chat-rag`. É uma
mudança pequena atravessando duas specs, então a decisão de onde o código novo
mora vale ser registrada.
