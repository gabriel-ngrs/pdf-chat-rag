# Backend do TalkDoc — os gates e o que cada um garante

Este documento não descreve o que o backend faz (isso está na spec e nas
docstrings dos módulos). Ele descreve **o que impede o backend de deixar de
fazer** — cada comando abaixo é um princípio do projeto convertido em algo que
falha. Um princípio que só existe em documento é uma intenção; `make arch`
quebrando quando alguém importa `asyncpg` dentro de `core/` é uma garantia.

Todos os comandos rodam a partir da raiz do repositório.

## O agregador

```
make check      # lint + typecheck + arch + test — precisa estar verde para uma fase fechar
make security   # bandit + pip-audit + npm audit
make test-db    # os testes que exigem o Postgres do compose
```

`make check` roda **offline**: sem rede, sem `GEMINI_API_KEY` e sem banco. Isso
é deliberado — quem clona o repositório precisa conseguir rodar a suíte inteira
antes de ter qualquer credencial.

---

## `make lint` — ruff

Estilo e um conjunto de regras de erro (`E`, `F`, `I`, `UP`, `B`, `SIM`), com
`line-length 100`. Garante que o código tenha uma forma só, que os imports
estejam ordenados e que armadilhas comuns de Python (`B`) não passem.

## `make typecheck` — mypy `--strict` sobre `app`

Toda função de `app/` tem tipos e eles fecham. `--strict` e não o modo padrão
porque o valor está justamente nos casos que o modo padrão perdoa: função sem
anotação, `Any` implícito, retorno não declarado. O único afrouxamento é
`ignore_missing_imports` para `asyncpg.*`, que não publica `py.typed` — está
comentado no `pyproject.toml` e não vale para mais nada.

## `make arch` — import-linter

Lê `backend/.importlinter`. **Se um contrato reprovar, muda o código, nunca o
contrato** — afrouxar uma linha daquele arquivo apaga exatamente a garantia
pela qual ele existe. Quatro contratos:

| Contrato | O que garante | Por que importa |
|---|---|---|
| **Camadas** `main → api → ingestion → adapters → core` | A dependência só aponta para baixo, e todo módulo de primeiro nível de `app` tem um lugar declarado na pilha (`exhaustive`) | Impede a inversão que tornaria a ingestão inalcançável para teste sem banco; um módulo novo sem posição na pilha quebra o gate em vez de escapar dele |
| **Núcleo puro** | `app.core` não alcança `fastapi`, `starlette`, `asyncpg`, `google`, `structlog`, `pypdf`, `pydantic(-settings)`, nem nenhum módulo das camadas de cima — **nem por import indireto** | O núcleo é a única parte que roda sem processo, sem rede e sem configuração. Logar já basta para perder isso: logging é efeito colateral, e um núcleo que loga passa a exigir configuração para ser testado |
| **Sem framework de RAG** | Nada importa `langchain*`, `llama_index*`, `langgraph` ou `haystack` | O RAG é o objeto da avaliação; terceirizá-lo apagaria as decisões de chunking, embedding e retrieval que a spec justifica linha a linha. Os pacotes são nomeados um a um porque `langchain_core` é uma distribuição separada de `langchain` |
| **Sem ORM nem query builder** | Nada importa `sqlalchemy`, `sqlmodel`, `tortoise`, `peewee` ou `databases` | Todo SQL é escrito à mão e parametrizado. Com um ORM no meio, o teste de injeção passaria a provar a segurança da biblioteca, não a deste projeto |

**O gate morde, e isso é testado.** `tests/test_architecture.py` cria
`app/core/_violacao_temporaria.py` com `import asyncpg`, roda o mesmo comando
que o `Makefile` roda e exige que ele falhe *nomeando o contrato violado* —
não basta o código de saída, porque um gate pode falhar por config inválida e
isso não provaria nada. O arquivo é removido num `finally`, e um terceiro teste
confirma que ele não sobreviveu. É o AC-24.

## `make test` — pytest

Suíte offline. Os testes marcados `@pytest.mark.db` ficam de fora e rodam por
`make test-db`, com o compose no ar.

## `make security`

### `bandit -q -r app`

Análise estática de padrões inseguros, restrita a `app`. O escopo é `app` e não
o repositório inteiro porque `bandit` sinaliza `assert` (B101) em todo teste, e
`assert` é o que um teste faz — a alternativa seria desligar a regra
globalmente, que é pior. Todo `# nosec` no código carrega o comentário que o
justifica; sem justificativa, ele não entra.

### `pip-audit`

Vulnerabilidades conhecidas nas dependências Python resolvidas do `uv.lock`.

### `npm audit --audit-level=high`

Vulnerabilidades do frontend. O corte em `high` é proposital: falha o gate por
severidade alta e registra as demais sem travar a entrega.

---

## As três propriedades de segurança, provadas por comportamento

`tests/test_security.py`. A diferença entre estes testes e uma afirmação em
documento é que aqui o segredo é realmente colocado no caminho do erro, o SQL
malicioso é realmente enviado ao Postgres e o nome de arquivo com travessia é
realmente enviado à rota.

**1. A chave não aparece em log (AC-19).** O pipeline de ingestão roda inteiro
com o renderizador JSON de produção, contra um provedor falso que ecoa a chave
em toda mensagem de erro (400, 429 com retry e 500 com esgotamento). A saída é
inspecionada byte a byte, e a asserção recusa não só a chave inteira como
qualquer fragmento de 8 caracteres dela — meia chave em log já é vazamento. A
`error_message` que o usuário vê também é verificada.

**2. Todo SQL é parametrizado.** Marcado `@pytest.mark.db` porque **precisa** do
Postgres real: contra um dublê em memória o teste provaria apenas que o dublê
não interpreta SQL. `find_by_hash` recebe `'; DROP TABLE chunks; --` em cada
parâmetro, e o mesmo payload é gravado e lido de volta literalmente. A prova não
é a consulta devolver `None` — é a tabela `chunks` continuar existindo e a
contagem de linhas não ter mudado depois. `get` recebe um UUID: o driver recusa
o payload antes de qualquer SQL, porque o valor é parâmetro tipado e não pedaço
de query.

**3. Nome de arquivo é nome, não caminho.** Um upload com `filename` igual a
`../../etc/passwd` (mais travessia absoluta, travessia do Windows, dupla
codificação e injeção de shell) é armazenado e devolvido **literal**, sem
`basename` e sem normalização. O teste troca o diretório de trabalho por um
vazio antes de enviar, de modo que qualquer escrita relativa — da rota ou da
task de background que ela agenda — apareceria ali; e confere que `/etc/passwd`
segue byte a byte igual.

---

## Lacuna conhecida

A redação da chave hoje acontece **no adapter**: `gemini.sanitize_message` limpa
a mensagem e `raise ... from None` impede que o traceback carregue o texto cru.
Isso cobre tudo que o adapter reconhece — `errors.APIError`, `TimeoutError` e
`OSError`.

Não é defesa em profundidade. Uma exceção que escape desse `except` chega ao
catch-all de `run_ingestion`, que chama `logger.exception`, e o traceback
serializado leva a mensagem crua. `httpx.ReadTimeout` é um exemplo real: não é
subclasse de `TimeoutError` nem de `OSError`, e o `google-genai` fala por httpx.

O teste `test_chave_nao_vaza_por_excecao_inesperada_no_traceback` está marcado
`xfail(strict=True)` justamente para que a lacuna viva na suíte, e não só num
relatório: no dia em que for corrigida, o teste passa a XPASS e falha, obrigando
quem corrigiu a transformá-lo em asserção de verdade.

Correção sugerida (código de produção, fora do escopo da fase que escreveu este
documento): um processador de redação em `app/logging_setup.py`, aplicado ao fim
da cadeia do structlog, removendo o segredo configurado de qualquer evento
renderizado — e/ou ampliar o `except` de `gemini._request` para cobrir as
exceções de transporte do httpx.
