---
spec: 01-ingestao-pdf
fase: A.2
slug_fase: pdf-chunking
tentativa: 1
veredito: RESSALVAS
score: 9.7
threshold: 8.5
range_avaliado: d6f42d3..a6438f85a9d35d29830a3eda0d5338e7ba09416e
---

# FASE A.2 — Avaliação independente

## 1. Veredito e score

**Veredito:** RESSALVAS · **Score:** 9.7 / threshold 8.5

Zero BLOQUEANTES. Um achado IMPORTANTE: a validação "PDF sem texto extraível"
conta **bytes**, não conteúdo, então um PDF cuja camada de texto é só espaço em
branco passa pelo guarda e o documento chega a `ready` com zero chunks.

O núcleo da fase — a citação exata por construção — foi verificado por mim,
independentemente dos testes do executor, contra o `Exemplo-YAITEC.pdf` real:
3 páginas, 10 chunks, **nenhum chunk cabe em outra página**, determinístico,
overlap real de 100 a 108 caracteres. É a melhor fase do track em relação
custo/prova.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 4 | AC-6, AC-7 e AC-4 provados por sonda independente (§6); AC-5 escapa quando o texto extraído é só espaço em branco (`app/adapters/pdf.py:64`) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `app/core/chunking.py` importa só `re` e `app.core.models`; `pypdf` fica confinado em `adapters/pdf.py`; contrato `pure-core` KEPT com `pypdf` na lista de proibições |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | Nenhum segredo tocado; mensagens de exceção citam só contagens e limites (`app/adapters/pdf.py:51-63`); erro cru do `pypdf` é trocado na fronteira (`:78`) para não vazar implementação |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `PageText`/`Chunk` vieram de `core/models.py`; as três exceções entraram na hierarquia `AppError` existente, sem hierarquia nova; `pyproject.toml` intocado |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `ValueError` para janela incoerente (erro de programação) vs `AppError` para erro do usuário — a distinção certa |
| 6 | Local e nomes dos arquivos | 2 | 5 | Exatamente os cinco arquivos da §5, mais `factories.py` previsto |
| 7 | Qualidade de código | 2 | 5 | `_cut_point`/`_next_start` curtas e nomeadas pela intenção; docstrings explicam a regra, não o passo (`app/core/chunking.py:40-53`) |
| 8 | Testes e cobertura | 2 | 5 | 25 testes; cobertura de `app/core/chunking.py` em 99% (branch) / 100% (linha); resultados reproduzidos por mim contra o PDF real |
| 9 | Migration safety | 2 | [—] | Não se aplica: a fase não toca schema |

Média ponderada: 97/100 → **9.7**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

### I-1 · "Sem texto extraível" mede bytes, não conteúdo — `backend/app/adapters/pdf.py:64`

```python
total = sum(len(page.text) for page in pages)
...
if total == 0:
    raise PdfWithoutTextError(NO_TEXT_MESSAGE)
```

`total` conta espaço em branco. Um PDF cuja camada de texto contenha apenas
espaços, tabulações ou quebras de linha — o que acontece com documentos gerados
a partir de imagem e com alguns geradores que emitem operadores de texto vazios —
tem `total > 0`, passa pelo guarda, e depois `normalize_whitespace` reduz tudo a
`""`, produzindo **zero chunks**. Medido por mim, ponta a ponta pela rota real:

```text
normalize('  \n \t '): ''
chunks de pagina so com espaco: []
estado: ready | chunks_total: 0 | erro: None
```

O usuário vê "pronto" e, na `FEAT-0002`, receberá a recusa "não encontrei isso no
documento" para toda pergunta — que é exatamente o diagnóstico errado, porque o
problema não é a pergunta, é o documento. O AC-5 existe para dar a esse usuário a
mensagem de OCR; aqui ela não sai.

A escolha é defensável contra a letra do passo 3 da §5 ("zero caractere
extraível"), e por isso é IMPORTANTE e não BLOQUEANTE — mas contra o AC-5 e
contra o usuário ela falha.

**Correção sugerida (uma linha):**

```python
total = sum(len(page.text.strip()) for page in pages)
```

e um teste com uma página cujo texto seja `"   \n  "` afirmando
`PdfWithoutTextError`. Vale também o guarda simétrico na `A.4` (ver a avaliação
daquela fase, S-1): documento sem chunk nenhum não deveria terminar `ready`.

## 5. Sugestões

- Os três `code` novos (`pdf_muitas_paginas`, `pdf_texto_longo`,
  `pdf_sem_texto`) continuam fora da tabela de §4.3. Hoje é inofensivo, porque só
  são levantados no background e chegam ao usuário pela `error_message` — o que
  a `A.4` de fato respeita. Vale acrescentá-los à §4.3 marcados como "só
  background", para que a próxima pessoa não descubra a regra por acidente.
- A lacuna que o próprio relatório declara (item 3 da §9) é real: o caminho
  "corte por parágrafo" só é exercitado com `PageText` sintético, porque a
  factory não produz `\n\n` depois do `pypdf`. Declarar foi o certo; fechar
  custaria um PDF de fixture com dois blocos separados por linha em branco.
- `_cut_point` procura o corte só na segunda metade da janela (`floor = size//2`).
  Está certo e é o que estabiliza a contagem de chunks — mas o valor merece
  virar constante nomeada, porque é decisão de produto (quantos chunks o PDF de
  exemplo gera) escondida numa expressão.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor a6438f85... HEAD   -> OK
$ cd backend && uv run ruff check .               -> All checks passed!
$ uv run mypy app                                 -> Success: no issues found in 18 source files
$ uv run lint-imports --config .importlinter      -> Contracts: 4 kept, 0 broken.
$ env -u GEMINI_API_KEY DATABASE_URL='postgresql://ninguem@127.0.0.1:1/x' uv run pytest -q
119 passed, 6 deselected in 6.99s

app/core/chunking.py      58      0     24      1    99%   78->80
```

**Sonda independente contra o `Exemplo-YAITEC.pdf` real (escrita por mim, não é
teste do executor):**

```text
paginas: 3 | chars por pagina: [1500, 1407, 758]
chunks: 10 | por pagina: {1: 4, 2: 4, 3: 2}
chunks cujo conteudo NAO esta na propria pagina: []
chunks que tambem cabem em outra pagina: []
determinismo: True
pares consecutivos na mesma pagina: 7 | overlap real: [106, 108, 101, 105, 103, 100, 104] | minimo exigido: 50
tamanhos: [367, 390, 397, 427, 447, 456, 465, 472, 473, 498]
maior chunk <= 500? True
```

Isso confirma, sem depender das asserções do executor: AC-6 (página correta,
nenhum chunk multi-página, determinismo), AC-7 (overlap ≥ `CHUNK_OVERLAP // 2`,
janela respeitada) e os "~10 chunks" que a spec projetava.

**Sonda do furo do AC-5 (escrita por mim):**

```text
$ POST /api/documents  (PDF com uma página contendo apenas espaços)
estado: ready | chunks_total: 0 | erro: None
```

## 7. Itens da fase / DoD não atendidos

- **AC-5 parcial** (I-1): a validação não pega camada de texto composta só de
  espaço em branco.
- Gate de conclusão atendido: testes verdes sem rede e sem banco, cobertura de
  `core/chunking.py` ≥ 90% (99% branch), `make check` zero.

## 8. Divergências entre o relatório e o código real

1. **"as três violações levantam a exceção certa (AC-4, AC-5)"** — verdadeiro
   para os casos testados, mas o caso de espaço em branco (I-1) não levanta
   nenhuma. O relatório não menciona essa fronteira.
2. O relatório fala em "16 testes de chunking" e "9 de extração"; a contagem
   confere (25 no total, reproduzidos por mim).
3. Os dois desvios declarados (assinatura keyword-only de `extract_pages`,
   `InvalidFileError` para PDF ilegível) conferem com o código e são bem
   justificados. O primeiro é melhor que a assinatura literal da spec.
