---
spec: 01-ingestao-pdf
fase: A.1
slug_fase: foundation
tentativa: 2
veredito: APROVADO
score: 9.5
threshold: 8.5
range_avaliado: 26ba58610514ac27c86595b01ee657795d382c92..8cc9eb14ab19faed861817a6e74ef2871b901c52
---

# FASE A.1 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.5 / threshold 8.5

O achado I-1 da tentativa 1 está fechado, verificado por sonda própria e por
mutação. O I-2 (fragmento da chave no histórico) segue aberto e **deixa de pesar
no veredito desta fase**, por reclassificação explicada em §4: não é defeito de
código nem coisa que o executor possa remediar — a remediação é rotacionar a
chave, ação do owner. Segue registrado como item aberto em §7 e continua sendo a
pendência mais séria da entrega, ainda que não desta fase.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | AC-17 agora vale para o literal: sonda mede `{code,message}` em 404 de rota e 405 (§6); `test_nenhuma_resposta_de_erro_usa_a_chave_detail` varre cinco caminhos e recusa a chave `detail` |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `lint-imports` 4/4 KEPT; o handler novo entrou em `app/errors.py:162-176`, junto dos outros três, sem espalhar tradução de erro pelas rotas |
| 3 | Segurança / LGPD / multi-tenant | 3 | 4 | Código e ponta da branch limpos (`git grep` só acha chaves falsas de teste); o repositório entregue ainda carrega o fragmento em `d6f42d3` |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `_HTTP_ERROR_CODES` reusa os `code` das subclasses existentes (`errors.py:106-111`) em vez de repetir literais |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Status sem código próprio caem em `erro_interno`: mantém fechada a tabela de §4.3, que é contrato dos dois tracks |
| 6 | Local e nomes dos arquivos | 2 | 5 | Alterações contidas em `app/errors.py` e `tests/test_errors.py` |
| 7 | Qualidade de código | 2 | 5 | Duas tabelas em vez de uma cadeia de `if`; a docstring do handler diz por que ele existe, citando o AC |
| 8 | Testes e cobertura | 2 | 5 | Três testes novos, e o terceiro é o que amarra o AC ao literal em vez de aos casos lembrados; mutação confirma (§6) |
| 9 | Migration safety | 2 | 5 | Schema inalterado nesta tentativa; conferido de novo contra Postgres a frio |

Média ponderada: 104/110 → **9.5**.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum.

**Reclassificação declarada do I-2 da tentativa 1.** O fragmento de 9 caracteres
da chave real em `d6f42d3` continua no histórico, e continua contrariando a
constitution ("nunca em arquivo versionado"). Não o mantenho como achado da fase
por três razões, e registro para que a decisão fique auditável:

1. O código e a ponta da branch estão limpos desde `34cb479`; não há o que
   corrigir em código.
2. A remediação real é **rotacionar a chave** — ação do owner, não do executor.
   Reescrever a `dev` com o Track B mergeado causaria mais estrago que o achado,
   e concordo com o executor nisso.
3. Manter um achado que nenhuma tentativa pode fechar prenderia a fase num ciclo
   de rework sem saída, contra o propósito do teto de tentativas.

Ele passa a viver em §7 como item aberto do owner. Não some.

## 5. Sugestões

- **405 com `code: erro_interno`** parece errado à primeira leitura e é
  deliberado — a alternativa seria acrescentar um sexto código à tabela de §4.3 e
  obrigar a B.2 a mapeá-lo. Concordo com a escolha. Se algum dia o mapa crescer,
  `metodo_nao_permitido` é o nome óbvio.
- `_HTTP_ERROR_MESSAGES` cobre 404, 405, 413, 422 e 429; qualquer outro status
  cai em `DEFAULT_HTTP_MESSAGE`. Vale um comentário dizendo que a ausência é
  intencional, para ninguém "completar" a tabela por reflexo.
- Item 2 da §9 (`atttypmod`): mantido, e continuo achando a escolha certa.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 8cc9eb14 HEAD   -> OK (ancestral de 7c2d6a4)
$ git status --porcelain                       -> (vazio; árvore limpa ao fim)

$ cd backend && uv run ruff check .            -> All checks passed!
$ uv run mypy app                              -> Success: no issues found in 18 source files
$ uv run lint-imports --config .importlinter   -> Contracts: 4 kept, 0 broken.
$ env -u GEMINI_API_KEY DATABASE_URL='postgresql://ninguem@127.0.0.1:1/x' uv run pytest -q
135 passed, 6 deselected in 10.12s
Required test coverage of 90% reached. Total coverage: 98.98%
$ cd frontend && npm run test   -> Test Files 6 passed (6) | Tests 40 passed (40)
```

**A mesma sonda da tentativa 1, agora com o resultado invertido:**

```text
GET    /api/rota-que-nao-existe   -> 404  chaves=['code','message']  {"code":"nao_encontrado","message":"O endereço pedido não existe."}
GET    /nao-existe                -> 404  chaves=['code','message']  {"code":"nao_encontrado", ...}
DELETE /api/config                -> 405  chaves=['code','message']  {"code":"erro_interno","message":"Este endereço não aceita esse método."}
```

**Mutação, escrita por mim (plugin de pytest que impede o registro do handler de
`StarletteHTTPException`, sem tocar no repositório):**

```text
=== sem mutação ===  7 passed
=== com mutação  ===
FAILED tests/test_errors.py::test_rota_inexistente_sai_no_envelope
FAILED tests/test_errors.py::test_metodo_nao_permitido_sai_no_envelope
FAILED tests/test_errors.py::test_nenhuma_resposta_de_erro_usa_a_chave_detail
3 failed, 4 passed
```

Os três testes novos denunciam a ausência da correção. Não são decorativos.

**Segredo em arquivos versionados (ponta da branch):**

```text
$ git grep -nIE "AIza[0-9A-Za-z_-]{10,}" -- .
(só as chaves falsas de tests/)
```

**`docker compose up --build` a frio — `[—]` NÃO RODADO por mim**, pela mesma
razão da tentativa 1: exige `GEMINI_API_KEY` e `.env`, que o avaliador não deve
manipular. O schema foi reconferido contra um Postgres descartável subido de
`db/001_init.sql` (`vector(768)`, HNSW `vector_cosine_ops`, `ON DELETE CASCADE`),
e os 6 testes sob o marker `db` passam contra ele.

## 7. Itens da fase / DoD não atendidos

- **Item aberto do owner, não da fase:** rotacionar a `GEMINI_API_KEY`. O
  fragmento em `d6f42d3` acompanha o repositório entregue. Se quiser história
  limpa, o momento é antes de adicionar o colaborador.
- Nada mais. O gate de conclusão da fase está atendido.

## 8. Divergências entre o relatório e o código real

Nenhuma. O que a §8 do EXECUCAO afirma sobre a correção, sobre a escolha do
`erro_interno` para status sem código próprio e sobre a mutação confere com o
código e com o que reproduzi de forma independente. O relatório também reconhece,
sem ser perguntado de novo, que a marcação `[x]` do AC-17 na tentativa 1 era mais
forte do que o código sustentava — registro honesto.
