---
spec: 01-ingestao-pdf
fase: A.2
slug_fase: pdf-chunking
tentativa: 2
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: d6f42d3..8cc9eb14ab19faed861817a6e74ef2871b901c52
---

# FASE A.2 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

O único achado da tentativa 1 está fechado, e fechado do jeito certo: a correção
veio acompanhada da **contrapartida** — o teste que garante que uma página em
branco ao lado de uma página com texto não derruba o documento. Sem ela, a
correção teria trocado um defeito por outro, rejeitando PDFs legítimos com folha
de rosto ou separador em branco. Rodei a mesma sonda da tentativa 1 e o
resultado se inverteu.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | AC-5 passa a valer para camada de texto vazia (`app/adapters/pdf.py:64-69`); AC-6/AC-7 reconferidos por sonda contra o PDF real (§6) |
| 2 | Arquitetura e direção de dependências | 3 | 5 | A decisão continua na fronteira: quem sabe o que é "texto" é o adapter; `core/chunking.py` segue importando só `re` e `app.core.models` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | Sem segredo, sem PII; mensagens de exceção citam contagens e limites |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Reusa `PdfWithoutTextError` e `NO_TEXT_MESSAGE`, que a `A.4` passou a importar em vez de repetir o texto (`app/ingestion.py:17`) |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Decidir por `strip()` alinha o adapter ao `normalize_whitespace` do núcleo — as duas noções de "vazio" passam a concordar de propósito, não por acaso |
| 6 | Local e nomes dos arquivos | 2 | 5 | Alterações contidas em `app/adapters/pdf.py` e `tests/test_pdf_extraction.py` |
| 7 | Qualidade de código | 2 | 5 | O comentário de quatro linhas diz por que `strip()` e não `len()`, citando o gerador de PDF que motiva a regra |
| 8 | Testes e cobertura | 2 | 4 | Quatro testes novos, incluindo a contrapartida; a lacuna declarada na §9 (a factory não produz `\n\n`, então o corte por parágrafo só é exercitado com `PageText` sintético) continua aberta |
| 9 | Migration safety | 2 | [—] | Não se aplica |

Média ponderada: 98/100 → **9.8**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

## 5. Sugestões

- **A §9 do EXECUCAO está desatualizada.** O item 1 ainda diz que
  "`extract_pages` ainda não é chamada por ninguém" — a `A.4` a chama desde a
  tentativa 1, dentro de `asyncio.to_thread`, que era exatamente o que aquele
  item pedia para conferir. Vale marcar como fechado, como foi feito com o item 1
  da §9 da `A.1`.
- A lacuna do item 3 continua real: o caminho "corte por parágrafo" nunca é
  exercitado por um PDF de verdade, porque o `pypdf` colapsa a linha em branco.
  Fecha com um PDF de fixture de dois blocos separados por linha em branco — e
  foi o executor quem declarou a lacuna, o que é o comportamento certo.
- `floor = max(1, size // 2)` em `_cut_point` continua sendo decisão de produto
  (quantos chunks o PDF de exemplo gera) escrita como expressão. Constante
  nomeada, quando houver folga.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 8cc9eb14 HEAD  -> OK
$ cd backend && uv run ruff check .           -> All checks passed!
$ uv run mypy app                             -> Success: no issues found in 18 source files
$ uv run lint-imports --config .importlinter  -> Contracts: 4 kept, 0 broken.
$ env -u GEMINI_API_KEY DATABASE_URL='postgresql://ninguem@127.0.0.1:1/x' uv run pytest -q
135 passed, 6 deselected in 10.12s
app/core/chunking.py      58      0     24      1    99%   78->80
```

**A sonda da tentativa 1, agora invertida (PDF com uma página só de espaços,
enviado pela rota real):**

```text
tentativa 1:  estado: ready  | chunks_total: 0    | erro: None
tentativa 2:  estado: failed | chunks_total: None | erro: PDF sem texto extraível;
              OCR não é suportado. Envie um PDF com camada de texto, não um
              documento escaneado.
```

**As propriedades centrais, reconferidas contra o `Exemplo-YAITEC.pdf` real para
garantir que a correção não mexeu no que já estava certo:**

```text
paginas: 3 | chars por pagina: [1500, 1407, 758]
chunks: 10 | por pagina: {1: 4, 2: 4, 3: 2}
chunks cujo conteudo NAO esta na propria pagina: []
chunks que tambem cabem em outra pagina: []
determinismo: True
overlap real: [106, 108, 101, 105, 103, 100, 104] | minimo exigido: 50
maior chunk <= 500? True
```

Nenhuma regressão: mesmos 10 chunks, mesmas fronteiras, mesmo determinismo.

## 7. Itens da fase / DoD não atendidos

Nenhum. O gate de conclusão (testes verdes sem rede e sem banco, cobertura de
`core/chunking.py` ≥ 90%, `make check` zero) está atendido e foi reproduzido.

## 8. Divergências entre o relatório e o código real

1. Nenhuma divergência material. O que a §8 afirma — inclusive a verificação de
   que `build_text_pdf(["   "])` extrai `'   '`, com `len_total=3`, que era
   exatamente o que passava pelo guarda antigo — confere com o comportamento que
   reproduzi.
2. Divergência menor, de higiene: a §9 não foi atualizada e mantém como aberto um
   item que a `A.4` fechou na tentativa 1 (ver §5).
