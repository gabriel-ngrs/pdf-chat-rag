---
spec: 02-chat-rag
fase: B.4
slug_fase: notices-persistence
tentativa: 2
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: 8a1e191..e696ab7
---

# FASE B.4 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

Os dois achados da tentativa 1 estão fechados, e reproduzi os dois por conta
própria: o I-1 na tela (sonda temporária) **e no banco do compose** (uma única
cópia da pergunta), e o gate dos códigos de erro pela evidência do turno real.
Zero BLOQUEANTES, zero IMPORTANTES.

**Correção da minha avaliação anterior:** eu registrei como pendência que o
código `provedor` da §4.3 não era emitido pelo servidor. **Estava errado.**
`ChatProviderError` já existia em `app/adapters/gemini.py:103` (`code = "provedor"`,
`status_code = 502`) desde antes da tentativa 1 — confirmei por
`git show 5acdb26:backend/app/adapters/gemini.py`. O erro foi meu: rodei
`grep -rn "provedor" backend/app/ | head` e o `head` cortou justamente as linhas
que importavam, e eu generalizei a partir de um grep em `app/errors.py`. Não
havia dívida da `A.4` nem nada a remover da spec, e o gate reproduziu o código
com `502` de verdade.

> **Nota sobre `range_avaliado`:** o EXECUCAO declara `8a1e191..74afd80`, a ponta
> da tentativa 1. Auditei o span real, que inclui `e76fbed`. Ver S-1 na `B.1`.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | Gate fechado: **sete** códigos reproduzidos contra o servidor real, incluindo `429` de quota de verdade e `502` de `provedor`; `F5` restaurou a conversa sem criar outra, e o `F5` no meio do stream trouxe a resposta marcada como interrompida (`gate-b/06`). Escopo travado: sem `alert()`, recusa ≠ erro, conversa não recriada, pergunta não se perde |
| 2 | Arquitetura e direção de dependências | 3 | 5 | Falha continua sendo estado do hook e a tela decide a recuperação; `mergeHistory` manteve a mescla dentro do dono do estado |
| 3 | Segurança / LGPD | 3 | 5 | Toda mensagem vem de `describeError(code)`; nenhum componente lê `ApiError.status`; nada de stack trace na tela nas capturas de erro (`gate-b/10`, `gate-b/12`) |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | Mapa de códigos estendido, canal único de avisos preservado |
| 5 | Padrões de domínio/aplicação | 2 | 5 | `documento_nao_pronto` sai como aviso **info** — confirmado na reprodução real, não só no teste |
| 6 | Local e nomes dos arquivos | 2 | 4 | `useNotices.ts` segue fora da lista da §5 (desvio declarado e correto). Soma-se o `backend/app/chat.py`, tocado por esta fase para fechar o lado servidor do I-1 — declarado no relatório como dívida da `A.4` que o defeito expunha, e visto pela reavaliação da `A.4` que veio depois |
| 7 | Qualidade de código | 2 | 5 | `_is_retry` (`chat.py:187-199`) resolve o caso pelo único sinal honesto disponível — conversa terminando em mensagem do usuário — e a docstring explica por quê |
| 8 | Testes e cobertura | 2 | 5 | A asserção que faltava entrou (conversa com 1 pergunta + 1 resposta após a repetição), com o contrapeso do cancelamento; no backend, `test_repetir_a_pergunta_que_falhou_nao_a_grava_duas_vezes` **e** o seu contrapeso para pergunta diferente; `errors.test.ts` voltou a ter tabela explícita código→severidade, exaustiva sobre `ERROR_CODES` |
| 9 | Migration safety | 2 | — | Não se aplica |

Média ponderada: 98/20 = 4,9 → **9.8/10**.

## 3. Achados BLOQUEANTES

Nenhum. O B-1 da tentativa 1 está fechado — os sete códigos foram provocados de
verdade (conversa inexistente, arquivo não-PDF, documento em processamento,
rajada até a quota real, banco derrubado, modelo inexistente, os dois
contêineres fora), e o `F5` foi exercitado nas duas variantes.

Duas observações minhas sobre a evidência, ambas favoráveis:

- A distinção que o relatório faz entre `erro_interno` e `rede_indisponivel` —
  com o nginx no ar e só o backend fora, o cliente recebe `502` do proxy e o
  aviso certo é `erro_interno`; `rede_indisponivel` é quando o `fetch` não chega
  a lugar nenhum — está correta e é exatamente o tipo de detalhe que só aparece
  quando se roda de verdade.
- `gate-b/06-f5-no-meio-do-stream.png` mostra o histórico restaurado **e** a
  marca "Resposta interrompida antes do fim." com ícone + texto, nunca só cor.
  Confirmei no banco o padrão correspondente: mensagens `#40/#41/#42` com
  `truncated = t`.

## 4. Achados IMPORTANTES

Nenhum. O **I-1 da tentativa 1 está corrigido dos dois lados**, e verifiquei
cada um deles sem depender do relatório.

**Cliente** (sonda temporária minha, removida em seguida; árvore limpa):

```text
APOS FALHA:   []
APOS REPETIR: ["Você perguntou: qual o e-mail?",
               "RespostaO TalkDoc respondeu:contato@exemplo.com.brpágina 2",
               "página 2"]                       ← o 3º <li> é o chip da citação
APOS CANCELAR: ["Você perguntou: resuma o documento"]   ← contrapeso preservado
```

A falha deixa **zero** balões e devolve a pergunta ao campo; a repetição produz
uma pergunta e uma resposta; e o cancelamento — que não é falha — **mantém** a
pergunta na conversa. É exatamente a distinção que `useChat.ts:192-197` faz.

**Servidor**, no banco do compose:

```text
copias_da_pergunta = 1
#59 user      'quais são os valores da empresa?'
#60 assistant  5 citações, truncated = f
```

Uma única linha para a pergunta que falhou e foi repetida — que é o que
`_is_retry` passou a garantir. Li a implementação com atenção ao falso positivo:
a conversa só termina em mensagem do usuário quando o turno anterior morreu
entre persistir a pergunta e produzir texto, e a comparação exige o conteúdo
idêntico. O único cenário de erro que consigo construir é duas abas perguntando
a mesma coisa na mesma conversa ao mesmo tempo — estreito o bastante para não
merecer código a mais.

## 5. Sugestões

- **Ver S-1 e S-2 na avaliação da `B.1`** (frontmatter fora do schema; e, aqui,
  o §9 do relatório ainda traz como "dúvida em aberto" o item 1 sobre
  `errors.test.ts` afrouxado, que o próprio rework já resolveu com a tabela
  explícita — vale limpar).
- **`_is_retry` mora em `backend/app/chat.py`, arquivo da `A.4`.** A mudança está
  declarada e é a certa (sem ela, o conserto do cliente esconderia a duplicação
  em vez de removê-la), mas o fato de uma fase do Track B alterar código de uma
  fase do Track A merece uma linha no relatório da `A.4` também — senão a
  história do arquivo fica só do lado de cá.
- **Achado do executor para a `A.4`, e é o mais sério do lote:** a criação
  preguiçosa do `Client` do Gemini não é segura sob concorrência — na rajada de
  18 perguntas simultâneas, 8 voltaram `500` com
  `RuntimeError: Cannot send a request, as the client has been closed`. Duas
  abas na primeira pergunta bastam para reproduzir. Não retém esta fase (é da
  `A.4`), mas é o tipo de falha que aparece justamente quando duas pessoas abrem
  a demonstração ao mesmo tempo.

## 6. Comandos rodados + saídas reais

```text
$ make check
Contracts: 4 kept, 0 broken.
Required test coverage of 90% reached. Total coverage: 99.55%
===================== 263 passed, 19 deselected in 14.35s ======================
 Test Files  10 passed (10)
      Tests  84 passed (84)

$ make security
No known vulnerabilities found | found 0 vulnerabilities | SEC_EXIT=0

$ grep -rn "alert(" frontend/src | wc -l        → 0
$ grep -rniE "gemini_api_key|sk-[a-z0-9]{10}" frontend/src | wc -l → 0

# correção do meu erro da tentativa 1
$ git show 5acdb26:backend/app/adapters/gemini.py | grep -n 'code = "provedor"'
    code = "provedor"        # já existia antes da tentativa 1

# I-1 no cliente (sonda temporária, removida)
$ npx vitest run src/components/__avaliacao_tmp.test.tsx
 Tests  2 passed (2)     (saídas coladas na §4)
$ rm -f src/components/__avaliacao_tmp.test.tsx

# I-1 no servidor
$ docker exec …db-1 psql -c "select count(*) from messages
    where conversation_id='dbde8a74-…' and role='user'
      and content='quais são os valores da empresa?'"
 1

# recusa pelo caminho real: token(recusa) → citations [] → done, sem chamar o LLM
$ curl -sN -X POST http://localhost:5173/api/conversations/<id>/messages …
event: token / event: citations {"citations": []} / event: done {"truncated": false}
# é a forma que `isRefusal` (MessageList.tsx:111-113) lê para marcar
# "sem base no documento" sem cara de erro — FR-6 e AC-19 casando de ponta a ponta

$ git status --short
(só um arquivo do Track A, de chat paralelo; nada meu)
```

## 7. Itens da fase / DoD não atendidos

Nenhum. Os itens abertos na tentativa 1 fecharam:

- "cada código de erro reproduzido exibe o aviso certo" ✅ — sete códigos,
  inclusive o `provedor` que eu havia dado por irreproduzível por engano;
- "um `F5` no meio da conversa restaura tudo" ✅;
- "não perder a pergunta quando o envio falha" ✅ — agora sem o balão órfão.

## 8. Divergências entre o relatório e o código real

- **A de S-1** (`range` desatualizado) e o §9.1 desatualizado citado nas sugestões.
- **Uma correção que corre no sentido oposto:** a divergência que eu apontei na
  tentativa 1 — o item "devolve a pergunta ao campo e oferece repetir" marcado
  como cumprido enquanto a tela duplicava a pergunta — deixou de existir: o
  comportamento agora é o que o item afirma, e o teste passou a olhar para o
  lugar certo.
- Nenhuma outra. Conferi o `_is_retry`, os dois testes de backend com contrapeso,
  a tabela de severidades e as capturas citadas.
