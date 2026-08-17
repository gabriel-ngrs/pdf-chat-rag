# Avaliações e verificações contra a API real

Aqui ficam registradas as verificações que **só a API de verdade pode responder** —
as que nenhum teste offline detecta porque o dublê, por construção, concorda com a
nossa expectativa. O registro existe para que a dúvida não volte: quem ler isto não
precisa gastar quota de novo para saber o que o provedor faz.

Nenhum teste do `make check` chama a rede. Os scripts desta pasta são rodados à mão.

---

## `scripts/check_embeddings.py` — comportamento de lote do `gemini-embedding-001`

**Pergunta:** quando três textos vão numa única requisição, o provedor devolve três
vetores ou um único vetor agregado?

**Por que importa:** o comportamento difere entre modelos do provedor. Com um vetor
agregado, o adapter gravaria vetores desalinhados dos chunks e o retrieval devolveria
trechos aleatórios — com a suíte inteira verde, porque o dublê devolve N vetores para
N textos. É a falha silenciosa mais cara desta spec.

**Como reproduzir** (a partir de `backend/`, com `GEMINI_API_KEY` no `.env` da raiz
do worktree):

```
uv run python scripts/check_embeddings.py
```

### Execução de 2026-08-17 — `google-genai 2.18.1`

```
modelo: gemini-embedding-001 | output_dimensionality: 768 | task_type: RETRIEVAL_DOCUMENT
[lista de strings] vetores devolvidos: 3 (esperado: 3)
[lista de strings]   vetor 0: dimensão=768
[lista de strings]   vetor 1: dimensão=768
[lista de strings]   vetor 2: dimensão=768
estratégia usada: lista de strings
norma L2 crua do vetor 0     = 0.589191
cos(gato, cachorro)          = 0.756068
cos(gato, mecânica quântica) = 0.715598
OK: lote devolve um vetor por texto e a similaridade é coerente.
```

Saída idêntica em duas execuções seguidas; código de saída `0`.

### O que ficou provado

| Pergunta | Resposta |
|---|---|
| Lote de N textos devolve N vetores? | **Sim** — 3 textos, 3 vetores, numa única requisição. |
| Foi preciso embrulhar cada texto num `Content`? | **Não.** `contents=["gato", "cachorro", "mecânica quântica"]` bastou. O caminho com `Content` continua no script, como fallback, caso o provedor mude. |
| `output_dimensionality=768` é respeitado? | **Sim** — todos os vetores vieram com 768 posições. |
| O vetor de 768 chega normalizado? | **Não.** A norma L2 crua foi **0.589191**. A normalização manual do adapter não é zelo: sem ela a distância de cosseno da `FEAT-0002` mentiria. |
| `cos(v0,v1) > cos(v0,v2)`? | **Sim** — 0.756068 > 0.715598. |

**Observação para quem for calibrar o `SIMILARITY_THRESHOLD` na `FEAT-0002`:** a margem
entre o par relacionado e o par não relacionado é estreita (0.0405). Palavras soltas
vivem numa região alta e comprimida do espaço deste modelo — 0.7156 entre "gato" e
"mecânica quântica" mostra que **similaridade alta em absoluto não significa
relevância**. O corte precisa ser calibrado contra chunks reais, nunca herdado desses
números.
