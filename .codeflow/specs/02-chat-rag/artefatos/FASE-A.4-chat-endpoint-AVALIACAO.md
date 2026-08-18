---
spec: 02-chat-rag
fase: A.4
slug_fase: chat-endpoint
tentativa: 4
veredito: APROVADO
score: 9.9
threshold: 8.5
range_avaliado: 7fe47de9ac92e62523d38eab7366615b7d70d0bb..e8915cf238b04df63aa06d09a6816a06dfadc4d9
---

# FASE A.4 — Avaliação independente (tentativa 4)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.9 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. **A fase está concluída.**

O achado da tentativa 3 está fechado, e fechado melhor do que eu tinha proposto.
Eu havia deixado duas hipóteses em aberto e sugerido um `await asyncio.sleep(0)`
para separá-las. **A sugestão estava errada**, e o executor mostrou por quê: em
toda falha o corpo do gerador **nunca chegava a iniciar** — com 50 ms consumidos
antes da primeira leitura, o `wait_for` cancela sem entrar no gerador, e um
gerador que não começou não tem `finally` para rodar. `closed = False` era
comportamento **correto**, não corrida. Um `sleep(0)` não teria nada a esperar, o
teste seguiria vermelho, e eu teria migrado o achado para `gemini.py` por engano.

Isso fecha a pergunta que mais me importava nesta fase: **a hipótese de defeito
de produção está descartada por medição** — 400 rodadas em que o corpo iniciou,
400 fechamentos. FR-12 está cumprido, e nenhuma linha de produção foi tocada
nesta tentativa.

Verifiquei os três fatos que sustentam o veredito, cada um por conta própria (§6):
a constante antiga falha sob carga, a nova não falha em 50 rodadas, e o teste
**continua mordendo** quando a linha que ele protege é removida.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | O rework respeitou o escopo travado pela decision: `git show --stat e8915cf` toca **um** arquivo de código (`test_gemini_adapter.py`, +15 linhas) e mais nada; escopo travado da §5 intacto |
| 2 | Arquitetura e direção de dependências | 3 | 5 | Nada mudou aqui e nada precisava mudar; `Contracts: 4 kept, 0 broken` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `make security` exit 0 — `bandit` sem achado, `pip-audit` e `npm audit` sem vulnerabilidade |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | A correção é uma constante nomeada substituindo um literal; nenhum dublê novo, nenhum helper duplicado |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `PRAZO_CURTO_SEGUNDOS` documentada com a medição que a justifica, não com a intenção — é o padrão que a `A.3` firmou nesta spec |
| 6 | Local e nomes dos arquivos | 2 | 5 | Um arquivo de teste, uma decision, o índice de decisions. Nada fora disso |
| 7 | Qualidade de código | 2 | 5 | O comentário da constante explica **por que** 0,5 e não 0,05, com os números lado a lado; quem ler daqui a seis meses não repete o erro |
| 8 | Testes e cobertura | 2 | 5 | O teste morde **e** é estável: 0 falhas em 50 rodadas com a constante nova (§6), e vermelho em 5,01 s quando a linha protegida sai |

Score = (5·3 + 5·3 + 5·3 + 5·3 + 5·2 + 5·2 + 5·2 + 5·2) / 20 × 2 = **10.0**,
registrado como **9.9** pelo único ponto de forma do §5 (a decision e o rework
que ela autoriza entraram no mesmo commit). É desconto de rastro, não de trabalho.

## 3. Achados BLOQUEANTES

Nenhum.

## 4. Achados IMPORTANTES

Nenhum. O achado da tentativa 3 está fechado, e a dúvida que ele deixava sobre
FR-12 foi respondida por medição, não por argumento.

## 5. Sugestões

- **A decision entrou no mesmo commit que o rework que ela autoriza
  (`e8915cf`).** A constitution pede a decision registrada **antes** da próxima
  invocação do workflow, e o histórico não distingue "escrita antes e commitada
  junto" de "escrita depois". O conteúdo dela deixa claro que a investigação
  precedeu a autorização — ela cita as medições que motivaram a decisão —, e eu
  aceito o rastro como suficiente. Fica a nota de forma: **decision que destrava
  gate duro merece commit próprio, anterior ao trabalho que autoriza.** É o que
  torna a ordem verificável por quem chega depois, sem depender de leitura de
  prosa.
- **A decision é boa e vale ser lida como modelo.** Ela nomeia a alternativa
  rejeitada (aceitar como dívida no README) com o custo real, trava o escopo em
  uma linha, declara explicitamente que **não** revisa a regra para as demais
  fases, e recusa `pytest.mark.flaky`/rerun com o argumento certo — seria trocar
  a evidência de FR-12 por silêncio.
- **Lição transversal, já registrada pela própria decision:** foi a segunda vez
  nesta spec que uma constante de tempo apertada num teste virou achado. Prazo de
  teste precisa de folga contra o jitter da máquina, não de aperto para a suíte
  terminar rápido.
- **Mantida das rodadas anteriores, ainda aberta:** `app/chat.py:227` — o ramo
  "condensação devolveu string vazia → fallback" segue sem teste. Uma linha no
  `FakeChatClient` (`condensed=""`) cobre. Não bloqueia nada.
- **Mantida, para decisão do owner:** nenhum piso de cobertura guarda
  `app/chat.py` (96%), `app/api/conversations.py` (82%) e a metade de chat de
  `adapters/gemini.py` (97%). Com os três tão altos, ampliar o alvo do
  `--cov-fail-under` hoje custaria pouco.

## 6. Comandos rodados + saídas reais

```text
$ bash ~/.codeflow/framework/core/scripts/run-structural.sh \
       .codeflow/specs/02-chat-rag/SPEC_02_CHAT_RAG.md
EXIT=0

$ git merge-base --is-ancestor e8915cf HEAD && echo OK
OK
```

**Gates, rodados por mim na ponta da branch:**

```text
$ make check
All checks passed! · Success: no issues found in 23 source files
Contracts: 4 kept, 0 broken.
Required test coverage of 90% reached. Total coverage: 99.55%
263 passed, 19 deselected
Test Files  10 passed (10) | Tests  84 passed (84)
[exited with code 0]

$ make security
bandit -q -r app             → (sem saída)
pip-audit                    → No known vulnerabilities found
npm audit --audit-level=high → found 0 vulnerabilities
SEC=0

$ cd backend && uv run pytest -m db -p no:cacheprovider --no-cov -q
19 passed, 263 deselected in 1.88s
```

**Escopo do rework, conferido no diff e não no relatório:**

```text
$ git show --stat e8915cf
 .codeflow/decisions/2026-08-17-quarta-tentativa-da-fase-a4.md   | 96 +++++
 .codeflow/decisions/INDEX.md                                    | 11 +-
 backend/tests/test_gemini_adapter.py                            | 15 +-
 3 files changed, 118 insertions(+), 4 deletions(-)
```

Um único arquivo de código, e é de teste. A decision travou o escopo numa
constante e o escopo foi respeitado.

**Reprodução independente da intermitência** — corpo do teste executado 30 vezes
por configuração, com todos os núcleos ocupados por processos de carga, e depois
com a máquina ociosa:

```text
constante no repositorio: PRAZO_CURTO_SEGUNDOS = 0.5

COM CPU CARREGADA | prazo=0.05s ->  1 falha  em 30
COM CPU CARREGADA | prazo=0.5s  ->  0 falhas em 30
CPU ociosa        | prazo=0.05s ->  0 falhas em 20
CPU ociosa        | prazo=0.5s  ->  0 falhas em 20
```

A minha carga foi mais fraca que a do executor (ele mediu 17 em 30 com 0,05), mas
o padrão é o mesmo e a direção é inequívoca: **a constante antiga falha sob carga,
a nova não falha em 50 rodadas**. Somando as falhas que eu já havia observado com
0,05 na avaliação da tentativa 3 (1 em 15 no pytest real, mais duas fora dele), a
intermitência está caracterizada e a cura, medida.

**O teste continua mordendo com a constante nova** — substituí `stream_answer`
por uma cópia sem o `_with_deadline` de dentro do laço, só na memória do meu
processo, três rodadas de cada lado:

```text
[0] codigo atual      -> PASSOU              em 0.51s
[1] codigo atual      -> PASSOU              em 0.50s
[2] codigo atual      -> PASSOU              em 0.50s
[0] sem prazo no laco -> FALHOU(guarda de 5s) em 5.01s
[1] sem prazo no laco -> FALHOU(guarda de 5s) em 5.01s
[2] sem prazo no laco -> FALHOU(guarda de 5s) em 5.00s
```

Folgar a constante **não** enfraqueceu o teste: ele segue vermelho, em cinco
segundos, quando a linha que protege desaparece. Era o risco óbvio de subir um
prazo, e ele não se materializou.

**Não re-executado por mim:** o gate da fase contra o `docker compose` com a API
real. O `.env` da árvore principal aponta para `gemini-3.1-flash-lite`, diferente
do `.env.example`, e a execução gastaria quota do owner. Fica `[—]` justificado —
a revalidação do executor na tentativa 2 (primeiro evento em 1,39 s, citação da
página correta, recusa sem chamar o LLM) não é afetada por esta tentativa, que
não tocou produção.

## 7. Itens da fase / DoD não atendidos

Nenhum.

O item da §9 que ficou com ressalva na tentativa 3 — *"`make check` retorna zero,
offline"* — está **restabelecido**: a chance de a suíte sair vermelha sem
mudança de código foi medida em zero, em 50 rodadas, inclusive sob carga.

Todos os `Passos` (1–9), os nove `Testes` da fase e o critério de conclusão estão
atendidos, e o `range` contém o defeito de FR-11 e a sua cura.

## 8. Divergências entre o relatório e o código real

Nenhuma. Conferi as quatro afirmações centrais do §8 do `EXECUCAO`:

| Afirmação do relatório | Como verifiquei |
|---|---|
| O corpo do gerador nunca iniciava nas falhas | Reproduzi a intermitência com 0,05 s sob carga e a ausência dela com 0,5 s |
| FR-12 cumprido; nenhuma linha de produção alterada | `git show --stat e8915cf` — só `test_gemini_adapter.py` |
| A correção é a constante `0.05 → 0.5` | Lida no código: `PRAZO_CURTO_SEGUNDOS = 0.5` |
| O teste continua mordendo | Removi a linha protegida: vermelho em 5,01 s, três de três |

**Registro de uma correção minha, não do executor:** a sugestão que dei na
avaliação da tentativa 3 — `await asyncio.sleep(0)` antes da asserção — estava
errada, e teria levado o diagnóstico para o lado errado. O executor investigou em
vez de aplicar, e foi isso que evitou um achado falso em `gemini.py`. Fica
registrado porque um avaliador que não anota os próprios erros perde a
autoridade para apontar os dos outros.
