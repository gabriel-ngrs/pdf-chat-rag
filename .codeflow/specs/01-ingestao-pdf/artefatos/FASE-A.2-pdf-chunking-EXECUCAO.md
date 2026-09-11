---
spec: 01-ingestao-pdf
fase: A.2
slug_fase: pdf-chunking
status: rework
tentativa: 2
reprovacoes: 1
sha_inicial: d6f42d3
sha_final: 8cc9eb14ab19faed861817a6e74ef2871b901c52
range: d6f42d3..8cc9eb14ab19faed861817a6e74ef2871b901c52
---

# FASE A.2 — Relatório de execução

## 1. Resumo do que foi feito

Bytes de PDF passam a virar chunks citáveis. `adapters/pdf.py` concentra o único
uso de `pypdf` e devolve `PageText` por página, com número base 1, aplicando as
três validações que exigem parse. `core/chunking.py` aplica a janela deslizante
com **reset a cada página** — é essa regra que torna a citação exata por
construção, e não uma heurística de "de qual página este trecho provavelmente
veio". Os PDFs de teste são montados byte a byte em memória: nenhum binário no
repositório, nenhuma dependência nova.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `backend/app/adapters/pdf.py` | `extract_pages(data, *, max_pages, max_chars)` — extração por página e as validações de parse |
| `backend/app/core/chunking.py` | `normalize_whitespace()` e `chunk_pages(pages, size, overlap)` — lógica pura de quebra |
| `backend/tests/factories.py` | Gerador de PDF mínimo em memória: `build_pdf`, `build_text_pdf`, `build_pdf_without_text_layer` |
| `backend/tests/test_pdf_extraction.py` | 9 testes de extração e das três validações |
| `backend/tests/test_chunking.py` | 16 testes de chunking: fronteira de página, determinismo, overlap, corte |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `backend/app/errors.py` | Três subclasses de `AppError` acrescentadas **após** `InternalError`, sem tocar no que existia: `PdfPageLimitError` (`pdf_muitas_paginas`, 422), `PdfTextLimitError` (`pdf_texto_longo`, 422), `PdfWithoutTextError` (`pdf_sem_texto`, 422) |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `PageText` e `Chunk` vieram de `app/core/models.py` (A.1),
não foram redefinidos. As exceções entraram na hierarquia `AppError` existente —
nenhuma hierarquia nova foi criada. `pypdf` já estava no `pyproject.toml`;
**nenhuma dependência foi adicionada**, e o `pyproject.toml` não foi tocado.

**Decisões de design.**

- **Corte procurado só na segunda metade da janela** (`floor = max(1, size // 2)`).
  Aceitar o primeiro parágrafo disponível produziria chunks minúsculos e um
  número de chunks refém da formatação do PDF. O `max(1, ...)` também garante
  progresso e impede laço infinito com `size` degenerado.
- **Overlap alinhado para trás**, ao espaço anterior ao alvo, nunca para frente:
  assim o trecho compartilhado nunca fica *menor* que o pedido. Medido com
  `size=500 / overlap=100`: compartilhamento real de 107 caracteres.
- **Normalização:** quebra de linha isolada vira espaço (é espúria, vinda da
  reconstrução por posição de glifo); duas ou mais viram exatamente `\n\n`,
  porque é fronteira de parágrafo legítima e ponto de corte preferencial.
- **`ValueError` para janela incoerente** (`size <= 0`, `overlap` fora de
  `[0, size)`) — é erro de programação, não do usuário, então não vira `AppError`
  e não ganha código de envelope.
- **Sanidade contra a spec:** uma página de ~1.220 caracteres com
  `CHUNK_SIZE=500` produz 3 chunks — exatamente a faixa "2 a 3" que a spec
  prevê. Conferido também contra o `documento-de-exemplo.pdf` real (3 páginas,
  1500/1407/758 caracteres), coerente com os ~10 chunks que a spec projeta.

**Desvios da spec — dois, ambos aditivos e declarados.**

1. **`extract_pages` recebe os limites como keyword-only obrigatórios**
   (`data: bytes, *, max_pages: int, max_chars: int`) em vez da assinatura
   literal `extract_pages(data: bytes)` que aparece no passo 2. O passo 3 exige
   que os limites sejam aplicados, e passá-los por parâmetro mantém o adapter
   independente de `Settings`, deixa os testes exercitarem os limites sem mexer
   em variável de ambiente, e concentra a resolução de configuração na borda.
   Keyword-only **obrigatório** (sem default) para não haver limite silencioso.
2. **PDF ilegível levanta `InvalidFileError`, classe já existente.** A spec lista
   três validações; arquivo corrompido ou protegido por senha não é nenhuma
   delas, mas o `pypdf` levanta `PdfReadError` cru, que vazaria detalhe de
   implementação na resposta da API. A troca acontece na fronteira (`_open` e
   `_extract`), reusando a hierarquia — sem classe nova.

**Ponto de contrato que o avaliador precisa ver (não é desvio, é consequência):**
os três `code` novos (`pdf_muitas_paginas`, `pdf_texto_longo`, `pdf_sem_texto`)
**não estão na tabela de cinco códigos da §4.3**, que é a que o `errors.ts` da
fase B.2 implementa. Isso é coerente com a FR-3: essas falhas acontecem **no
background**, e chegam ao usuário pela `error_message` do documento, que a B.4
exibe literalmente — não pelo envelope HTTP. **Consequência para a A.4:** essas
três exceções não podem ser levantadas no caminho da requisição, só dentro do
pipeline. Se forem, o frontend receberá um `code` que não sabe mapear.

Nenhuma violação do escopo travado: `core/chunking.py` importa só `re` e
`app.core.models` (`make arch` confirma), não há splitter de terceiros, não há
OCR, nenhum PDF binário foi commitado, e nenhum chunk cruza fronteira de página.

## 5. Comandos rodados + saídas reais

```text
# lint — uv run ruff check app/adapters/pdf.py app/core/chunking.py app/errors.py \
#          tests/factories.py tests/test_pdf_extraction.py tests/test_chunking.py
All checks passed!

# type-check — uv run mypy app
Success: no issues found in 14 source files

# arquitetura — uv run lint-imports --config .importlinter
Analyzed 31 files, 33 dependencies.
Camadas: api -> adapters -> core KEPT
Nucleo puro: core nao conhece I/O nem framework KEPT
Sem framework de RAG KEPT
Contracts: 3 kept, 0 broken.

# testes da fase — uv run pytest tests/test_pdf_extraction.py tests/test_chunking.py -q
.........................                                                [100%]
25 passed in 0.50s

# regressão: fase A.2 + fase A.1 juntas (verificação independente do orquestrador)
# uv run pytest tests/test_pdf_extraction.py tests/test_chunking.py tests/test_errors.py \
#               tests/test_health.py tests/test_config.py tests/test_lifespan.py -q
.........................................                                [100%]
41 passed in 2.18s

# cobertura — uv run --with pytest-cov pytest tests/test_chunking.py -q \
#               --cov=app.core.chunking --cov-report=term
Name                   Stmts   Miss  Cover
------------------------------------------
app/core/chunking.py      58      0   100%
------------------------------------------
TOTAL                     58      0   100%
16 passed in 0.09s

# segurança — [—] NÃO RODADO nesta fase
# Justificativa: `make security` (bandit + pip-audit + npm audit) é o entregável
# da fase A.6, que o declara como critério de conclusão. Rodá-lo aqui não
# provaria nada desta fase.

# frontend (lint + tsc) — [—] NÃO RODADO
# Justificativa: mesma da A.1 — frontend/src é entregável do Track B, em
# execução paralela em outra branch.
```

Nota operacional: `--cov=app/core/chunking` (com barra) emite
`CoverageWarning: module never imported` e não coleta nada; a forma que funciona
é `--cov=app.core.chunking` (com ponto). O `.coverage` gerado foi removido, e
`pytest-cov` foi usado via `uv run --with`, sem alterar o `pyproject.toml`.

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-4** (páginas acima do limite → `failed` citando o limite de páginas) —
  `test_paginas_acima_do_limite_levantam_erro_de_paginas` levanta
  `PdfPageLimitError` com a mensagem citando as 5 páginas e o limite 4;
  `test_pagina_no_limite_exato_de_paginas_e_aceita` prova que o limite não é
  off-by-one. O caso de caracteres:
  `test_texto_acima_do_limite_de_caracteres_levanta_erro_de_texto`
  (`PdfTextLimitError`).
- [x] **AC-5** (sem texto extraível, OCR não suportado) —
  `test_pdf_sem_camada_de_texto_avisa_que_ocr_nao_e_suportado` assere
  `PdfWithoutTextError` e que a mensagem contém "sem texto extraível" **e**
  "ocr". `test_as_tres_violacoes_de_parse_tem_codigos_distintos` prova que os
  três `code` são distintos, que é o que permite mensagem específica por caso.
- [x] **AC-6** (página correta, nenhum chunk multi-página, determinismo) —
  `test_cada_chunk_carrega_o_numero_da_pagina_de_origem`;
  `test_nenhum_chunk_contem_texto_de_duas_paginas` (marcadores `A`/`B` por
  página, nenhum chunk contém os dois);
  `test_duas_execucoes_produzem_resultado_identico`;
  `test_extracao_e_deterministica_entre_execucoes`;
  `test_paginas_sao_processadas_na_ordem_e_o_indice_e_sequencial`.
- [x] **AC-7** (corte não parte palavra; overlap ≥ `CHUNK_OVERLAP // 2`) —
  `test_nenhum_chunk_comeca_ou_termina_no_meio_de_palavra` confere cada fronteira
  contra o texto normalizado;
  `test_chunks_consecutivos_da_mesma_pagina_compartilham_o_overlap_minimo`
  calcula o maior sufixo/prefixo comum e exige ≥ `OVERLAP // 2` (real medido:
  107 com `overlap=100`). Complementares:
  `test_o_corte_prefere_a_fronteira_de_paragrafo`,
  `test_o_corte_cai_no_fim_de_sentenca_quando_nao_ha_paragrafo`,
  `test_o_corte_cai_no_espaco_quando_nao_ha_sentenca_nem_paragrafo`,
  `test_palavra_maior_que_a_janela_e_cortada_no_limite_duro`.
- [x] **AC-29 (a parte desta fase)** — cobertura de `app/core/chunking.py` em
  **100%** (≥ 90% exigido), saída colada acima. Toda função pública e privada de
  `pdf.py` e `chunking.py` tem docstring dizendo o que faz **e por quê**; a de
  `chunk_pages` afirma explicitamente que não cruzar página é o que torna a
  citação exata por construção.
- [x] **Página menor que a janela vira um chunk** —
  `test_pagina_menor_que_a_janela_vira_um_unico_chunk`; e
  `test_pagina_sem_texto_nao_gera_chunk`.

## 7. Definition of Done da fase

- [x] Testes da fase verdes — 25 passando, sem rede e sem banco.
- [x] Comandos de validação limpos nos arquivos tocados — ruff, mypy strict e
      lint-imports zerados. `security` e gates de frontend `[—]` justificados.
- [x] Escopo travado respeitado — nenhuma violação BLOQUEANTE da §5.
- [x] Nenhum segredo/PII em log/DTO/exceção — esta fase não emite log nem toca
      em segredo; as mensagens de exceção citam só contagens e limites.
- [x] Commits em pt-BR (Conventional Commits).

## 8. (Em rework) O que mudou nesta tentativa

Tentativa 2, motivada pelo veredito **RESSALVAS** (score 9,7). Um achado
IMPORTANTE, zero BLOQUEANTES.

### I-1 · "Sem texto extraível" media bytes, não conteúdo — CORRIGIDO

O guarda somava `len(page.text)`. Um PDF cuja camada de texto contém apenas
espaço, tabulação ou quebra de linha — o que acontece com documento vindo de
imagem e com geradores que emitem operadores de texto vazios — tinha
`total > 0`, passava, e depois `normalize_whitespace` reduzia tudo a `""`,
produzindo **zero chunks**. O documento terminava `ready` sem conteúdo, e na
`FEAT-0002` toda pergunta receberia "não encontrei isso no documento": o
diagnóstico errado, porque o problema é o documento, não a pergunta. O usuário
do AC-5, que deveria ler o aviso de OCR, não o lia.

Correção em `app/adapters/pdf.py`, decidindo por conteúdo:

```python
if not any(page.text.strip() for page in pages):
    raise PdfWithoutTextError(NO_TEXT_MESSAGE)
```

Confirmei que a factory reproduz exatamente o caso: `build_text_pdf(["   "])`
extrai `'   '` — `len_total=3` (passava no guarda antigo) e `strip()` vazio.

Quatro testes novos em `tests/test_pdf_extraction.py`: três parametrizados para
o caso vazio, **e um que garante a contrapartida** — uma página em branco ao
lado de uma com texto não derruba o documento. Sem essa contrapartida, a
correção passaria a rejeitar PDFs legítimos com folha de rosto ou separador em
branco. **Verificado por mutação:** voltando a `if total == 0`, os testes falham.
Medido também ponta a ponta no compose: o documento agora termina `failed` com a
mensagem de OCR.

### Guarda simétrico na A.4 (sugestão S-1, cruzada entre as duas avaliações)

A avaliação desta fase pedia também o guarda do outro lado. Implementado em
`app/ingestion.py`: se o chunking devolver lista vazia, o documento termina
`failed` em vez de `ready`. Registrado no relatório da A.4, com a ressalva
honesta de que hoje ele é **inalcançável** — as duas noções de "vazio"
concordam — e de como isso foi testado sem fingir um PDF que o dispare.

## 9. Itens em aberto / dúvidas para o avaliador

1. **`extract_pages` ainda não é chamada por ninguém.** A integração com
   `asyncio.to_thread` é da A.4. A docstring instrui o chamador, mas **nada
   nesta fase detecta se a A.4 esquecer o `to_thread`** — se esquecer, o event
   loop trava e a suíte continua verde. Vale conferir na avaliação da A.4.
2. **`InvalidFileError` para PDF corrompido é decisão do executor**, não da spec
   (desvio 2). Se o avaliador quiser um `code` próprio para "PDF ilegível", é
   uma linha em `errors.py` — mas aí ele entra na tabela §4.3 e a B.2 precisa
   mapeá-lo.
3. **A factory não produz parágrafos (`\n\n`) no texto extraído**, porque o
   heurístico do `pypdf` colapsa linha em branco em `\n`. Consequência real: o
   caminho "corte por parágrafo" é exercitado com `PageText` sintético, não com
   um PDF de verdade. É defensável (isola o chunking do parser), mas é uma
   lacuna de fidelidade end-to-end e eu prefiro declará-la a escondê-la.
4. **Os três códigos novos fora da tabela §4.3** — ver §4 acima. Não é problema
   hoje, mas vira um se a A.4 levantá-los no caminho da requisição.
