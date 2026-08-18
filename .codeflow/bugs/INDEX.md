# Bugs do teste de ponta a ponta — FEAT-0002

Duas rodadas de teste, antes da fase `B.5`. Nenhum bug se conserta dentro da
`B.5`: cada um volta como rework da fase dona ou como `/bugfix`, conforme a
pré-condição registrada na spec.

| rodada | quando | como | achados | estado |
|---|---|---|---|---|
| 1ª | 2026-08-17 | teste manual do owner | 001–005 | **corrigidos e verificados** |
| 2ª | 2026-08-18 | roteiro automatizado com Playwright | 006–010 | **abertos** |

---

## 1ª rodada — 2026-08-17 · corrigida

> **Os cinco foram corrigidos em 2026-08-17** pelo lote
> `feat-0002-teste-ponta-a-ponta` — ledger em
> `.codeflow/bug-batches/feat-0002-teste-ponta-a-ponta.md`, decisões em
> `.codeflow/decisions/2026-08-17-lote-de-bugs-do-teste-de-ponta-a-ponta.md`.
> "Corrigido" aqui significa: fix aplicado, teste de regressão passando e
> reprodução do relato refeita contra a API real. **O `/double-check` rodou em
> 2026-08-18 e confirmou os cinco** — placar 5 ✓ · 0 ✗ · 0 ⚠, com cada teste de
> regressão reexecutado contra o código pré-fix e a reprodução refeita no
> compose. O veredito por bug está na seção "Verificação" do ledger.

| # | Título | Severidade | Fase dona | Status |
|---|--------|-----------|-----------|--------|
| [001](001-condensacao-nao-dispara-em-pergunta-de-4-palavras.md) | Continuação de 4 palavras não condensa e vira recusa falsa | **alta** | A.2 | corrigido |
| [002](002-limiar-de-similaridade-recusa-perguntas-legitimas.md) | Limiar 0,625 recusa perguntas que o documento responde | **alta** | A.5 | corrigido |
| [003](003-citacoes-mostram-chunks-recuperados-nao-usados.md) | Citações exibem os chunks recuperados, não os usados | média | A.4 | corrigido |
| [004](004-mensagem-de-quota-promete-um-minuto-mas-o-limite-e-diario.md) | Mensagem de quota promete "um minuto"; o limite é diário | média | B.4 / A.4 | corrigido |
| [005](005-resposta-cita-trecho-n-que-nao-existe-na-interface.md) | Resposta cita "Trecho N", rótulo que não existe na tela | média | A.2 | corrigido |

### Os dois que mais pesavam

**001 e 002 se somavam** e produziam o mesmo sintoma pela frente: recusa em
pergunta que o documento responde. A continuação não condensada chegava ao
retrieval como frase vazia e pontuava `0,527`; perguntas curtas sem a âncora
"YAITEC" pontuavam entre `0,53` e `0,62`. O corte estava em `0,625`.

A recusa é o mecanismo que o desafio avalia com mais peso. Falsa recusa é o pior
modo de falha: o sistema tem a informação, foi perguntado com clareza, e diz que
não sabe.

**003 e 005 se somavam** também, e do lado da interface: cinco chips com rótulos
repetidos, e o texto apontando para uma numeração que não existe na tela.

### Confirmados de pé na 2ª rodada

A segunda rodada reexecutou os cenários dos cinco. Todos continuam corrigidos:

- **001** — `e a formação dele?` e `e quem mora longe de lá?` condensam com LLM
  (`chat.condensed` com `used_llm: true`) e respondem sobre o assunto certo.
- **002** — com o limiar em `0,561`, nenhuma pergunta legítima foi recusada em
  45 tentativas; as duas recusas verdadeiras pontuaram `0,527` e `0,497`.
- **003** — o rótulo é "trechos consultados", e o diálogo explica que nem todo
  trecho aparece na resposta.
- **004** — a mensagem de quota fala das duas cotas do plano gratuito, sem
  prometer prazo.
- **005** — nenhuma das 45 respostas citou "Trecho N"; todas citam a página.

---

## 2ª rodada — 2026-08-18 · aberta

Roteiro de ponta a ponta executado com Playwright (Chromium headless, 1440×900)
contra o stack em `docker compose` a partir de `down -v`. Cada item conferido em
quatro lugares: tela, chamada de API, evento de log estruturado e linha no
Postgres. Relato completo em `RESULTADO-DO-TESTE.md`, na raiz.

| # | Título | Severidade | Fase dona | Status |
|---|--------|-----------|-----------|--------|
| [006](006-conversa-longa-nao-rola-por-dentro.md) | Conversa longa para de rolar por dentro e empurra o campo de pergunta para fora da tela | **alta** | B.1 (regressão em `df3ac95`) | aberto |
| [007](007-pergunta-longa-recebe-mensagem-de-pdf-invalido.md) | Pergunta acima de 2.000 caracteres volta como "arquivo não é um PDF válido" | média | A.1 + B.2 | aberto |
| [008](008-barra-de-progresso-nao-avanca-no-pdf-de-exemplo.md) | Barra de progresso fica em 0% e some, no PDF da demonstração | média | A.4 (ingestão) | aberto |
| [009](009-condensacao-estoura-o-timeout-e-custa-cinco-segundos.md) | Condensação estoura os 5 s e custa 5 segundos parados | baixa | A.2 | aberto |
| [010](010-turno-interrompido-nao-deixa-evento-de-fecho-no-log.md) | Turno interrompido não deixa evento de fecho no log | baixa | A.4 (chat) | aberto |

### O que pesa

**006 é o único que aparece sozinho.** Não exige entrada estranha, falha de
rede nem quota estourada — só uma conversa de tamanho normal. A partir de ~8
mensagens a conversa abre na primeira pergunta em vez da última resposta, o
acompanhamento do fim fica inerte, e o campo de pergunta sai da tela. É
regressão datada: `df3ac95` trocou o `calc(100dvh - 14rem)` do `ChatView` por
`h-full` sem trocar o `min-h-dvh` do `AppShell` por altura definida.

**007 e 008 são os que um avaliador tropeça sem procurar.** Um manda conferir um
PDF que está perfeito; o outro é a primeira coisa que a demonstração mostra.

**009 e 010 podem esperar**, mas o 010 vale antes da entrega: "turno que começa
e nunca termina" lê no log como bug maior do que é.

### O que não é bug

- **Os chips de citação são quase sempre os mesmos cinco.** Com
  `RETRIEVAL_TOP_K=5` num documento de 10 chunks, metade do documento passa do
  limiar em quase toda pergunta, e o primeiro chip costuma ser o cabeçalho da
  página 1. É o **resíduo aceito do [BUG-003](003-citacoes-mostram-chunks-recuperados-nao-usados.md)**:
  o caminho escolhido lá foi renomear para "trechos consultados", não filtrar
  pelos usados. A tela deixou de mentir; a lista continua larga. Fica registrado
  aqui porque, numa demonstração, o primeiro chip que o avaliador clicar tende a
  abrir um trecho irrelevante — vale uma frase no README, não um fix.
- **A quota não foi reproduzida.** 12 requisições em paralelo passaram todas, e
  as ~45 perguntas da rodada não atingiram limite nenhum. O caminho de erro foi
  verificado injetando o evento `error` com `code: limite_de_uso` no stream, e
  se comportou: aviso claro, ação de repetir, pergunta preservada no campo e
  sem duplicação ao reenviar.
- **Fora isso, o resto do roteiro passou.** Ingestão, deduplicação por hash,
  os três limites de upload, streaming token a token, recusa em 0,82 s sem
  chamar o modelo, condensação nas duas continuações, cancelamento, `F5` no meio
  do stream, offline e volta, percurso de `Tab`, foco visível, contraste AA nos
  dois temas, e nenhum rastro da chave em log nenhum.

### Verificações que não estavam no roteiro

Feitas junto, e todas de pé:

- A chave real de 53 caracteres não aparece em log de nenhum serviço, nem
  fragmentos de 12 caracteres dela, nem no bundle servido pelo nginx.
- Os 180 chunks do banco têm embedding de 768 dimensões, nenhum nulo.
- Índices presentes: `chunks_embedding_idx`, `chunks_tsv_idx`,
  `messages_conversation_id_created_at_idx`, `conversations_document_id_idx` e
  `documents_session_id_content_hash_key`.
- Build a frio (`--no-cache`): backend 26,1 s + frontend 57,9 s ≈ 1 min 24 s.
  Com cache quente, 17,6 s do `down -v` ao stack saudável.
