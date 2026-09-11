---
id: BUG-005
titulo: "A resposta cita 'Trecho N', um rótulo interno do prompt que não existe na interface"
descoberto_em: 2026-08-17
descoberto_por: teste de ponta a ponta do owner (telas dos blocos 3 e 5)
severidade: média
fase_dona: A.2 (core-prompting)
status: corrigido e verificado (/double-check 2026-08-18)
---

# BUG-005 — Referência pendurada: "Trecho 5" não existe na tela

## Sintoma

O texto das respostas cita trechos por número, e esse número **não aparece em
lugar nenhum da interface**. Das telas do teste:

| pergunta | o que a resposta diz | o que a tela oferece |
|---|---|---|
| `Quem fundou a empresa?` | "consta na página 2 **(Trechos 1 e 2)**" | chips: página 1, 2, 2, 3, 3 |
| `contato@exemplo.com.br` | "página 3, **Trecho 5**" | chips: página 1, 2, 2, 3, 3 |
| `A empresa trabalha com a Empresa-X?` | "conforme o **Trecho 1**, página 2" | chips: página 1, 1, 2, 2, 3 |
| `sigla do documento` | "página 2, **Trechos 1 e 2**" | chips: página 1, 2, 2, 3, 3 |

Quem lê "Trecho 5" procura o trecho 5 e não encontra: os chips são rotulados só
por página.

## Causa raiz

`backend/app/core/prompt.py:21` envelopa cada trecho com um marcador numerado:

```python
CHUNK_OPEN_TEMPLATE = "<<<TRECHO {index} | pagina {page}>>>"
```

O número é **posição no prompt**, criado para o modelo distinguir um bloco do
outro — a docstring de `_render_chunks` diz isso com todas as letras. Mas as
instruções (`ANSWER_INSTRUCTIONS`) pedem apenas *"Diga de qual página veio cada
informação"*, e não proíbem citar o rótulo. O modelo, sendo obediente, cita os
dois — e o rótulo interno vaza para o usuário.

A interface nunca teve rótulo de trecho: `CitationChip.tsx:43` monta o
`aria-label` como `"ver trecho da página N"`, e o texto visível é só `página N`.

## Agravante: páginas repetidas nos chips

Como o top-k traz cinco chunks e o documento tem três páginas, os chips repetem:
`página 1 · página 2 · página 2 · página 3 · página 3`. Mesmo que o usuário
ignore o "Trecho N" e vá pela página, **dois chips diferentes dizem a mesma
coisa** e não há como saber qual sustenta a afirmação.

Somado ao [BUG-003](003-citacoes-mostram-chunks-recuperados-nao-usados.md), o
efeito é: cinco fontes na tela, rótulos ambíguos, e o texto apontando para uma
numeração que não existe.

## Correção sugerida

A mais barata, e que resolve sozinha: **acrescentar uma instrução** em
`ANSWER_INSTRUCTIONS` dizendo para citar **apenas a página**, nunca o número do
trecho — algo como *"Refira-se às fontes só pelo número da página; não mencione
os marcadores de trecho."*

Alternativa mais ambiciosa, se quiser manter a numeração: rotular os chips com
o mesmo número (`Trecho 5 · página 3`), o que também resolve a ambiguidade dos
chips repetidos. Custa mudança na `B.3` além da `A.2`, e amarra o rótulo da
interface à posição no prompt — acoplamento que hoje não existe.

Recomendo a primeira. A segunda só se o BUG-003 for resolvido junto.

## Encaminhamento

Rework da `A.2`, dona de `core/prompt.py` e de `tests/test_prompt.py`. Um teste
de que a instrução está presente cobre a mudança; asserir sobre o texto que o
modelo gera não vale, e o escopo travado da `A.6` proíbe.

---

**Corrigido em 2026-08-17** pelo lote `feat-0002-teste-ponta-a-ponta`
(`.codeflow/bug-batches/feat-0002-teste-ponta-a-ponta.md`). O fix, o teste de regressão e a reprodução manual estão na linha
deste bug no ledger; as escolhas não-triviais estão em
`.codeflow/decisions/2026-08-17-lote-de-bugs-do-teste-de-ponta-a-ponta.md`. O
`/double-check` rodou em **2026-08-18** e marcou este bug como **sanado (✓)**: o
teste de regressão falha contra o código pré-fix e a reprodução do relato foi
refeita. Detalhe na seção "Verificação" do ledger.
