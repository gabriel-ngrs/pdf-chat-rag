# Resultado do roteiro de teste — TalkDoc

Executado em 18/08/2026 com Playwright (Chromium headless, 1440×900) contra o
stack completo em `docker compose`, a partir de um banco zerado (`down -v`).
Cada item foi verificado na tela **e** no que ele produz atrás dela: chamada de
API, evento de log estruturado e linha no Postgres.

**Placar:** 2 `[falhou]`, 3 `[estranho]`, o resto `[ok]`.
Um item não pôde ser reproduzido (quota real do provedor) e foi coberto por
simulação do evento de erro.

---

## 0. Ponto de partida

- [ok] `docker compose up --build` a partir de um estado limpo (`down -v` antes)
- [ok] Cronometragem — **17,6 s** do `down -v` ao stack saudável, com cache de
      build quente. A frio (`--no-cache`): backend **26,1 s** + frontend
      **57,9 s** = **~1 min 24 s** de build, mais alguns segundos de subida.
      Bem abaixo dos ~4 min que o roteiro usava como alerta — número seguro para
      o README. O tempo a frio é dominado pelo `npm ci` do frontend.
- [ok] `curl -s http://localhost:8000/api/health` → `{"status":"ok","database":"ok"}`
- [ok] `http://localhost:5173` abre em 4,0 s, título `TalkDoc — converse com o seu PDF`

---

## 1. Upload e ingestão

- [estranho] **A barra de progresso não avança com o `Exemplo-YAITEC.pdf`.**
      Amostrando o DOM a cada 120 ms, o único valor observado foi
      `0 de 10 trechos · 0%`; 2,2 s depois a tela já era o chat.
      Causa: o PDF vira 10 chunks e `EMBEDDING_BATCH_SIZE=16`, então tudo cabe
      em **um** lote — `update_progress` é chamado uma vez só, no fim
      (`ingestion.py:141`). Não é defeito de código: com um PDF de 20 páginas
      seriam ~5 lotes e ~5 passos. Mas é justamente o arquivo da demonstração
      que exibe o comportamento que o roteiro queria evitar.
- [ok] Ao terminar, a UI leva sozinha até o chat — 6,4 s do clique ao campo de
      pergunta, sem nenhum clique intermediário
- [ok] Subir o mesmo PDF de novo reaproveita: mesmo `document_id`, 2,3 s contra
      6,4 s, e `{"event":"document.duplicate"}` no log. Nenhum chunk novo no banco
- [ok] Arquivo que não é PDF → *"Arquivo não é um PDF válido / Só é possível
      enviar arquivos PDF."* Recusado no cliente, sem chegar ao servidor
- [ok] PDF de 26,4 MB → *"O arquivo tem 25,2 MB e o limite é 25 MB."*
- [ok] PDF de 27 páginas → *"O PDF tem 27 páginas e o limite é 20. Envie um
      documento menor."* Recusa no servidor, documento fica `failed` com a
      mensagem exibida na tela

---

## 2. O caminho feliz do chat

- [ok] `Quem fundou a YAITEC?`
  - **primeiro token em 1,38 s** (limite: 5 s)
  - token a token confirmado com `MutationObserver`: numa resposta longa foram
    **15 incrementos** de ~80–120 caracteres ao longo de 1,4 s. Em resposta
    curta chega em 1–2 pedaços, porque a resposta inteira cabe neles
  - o "pensando" aparece antes do primeiro token e some quando ele chega
    (medido nos dois sentidos)
- [ok] Chip de citação abre o trecho com a página no título e a similaridade
- [ok] **Conferência à mão contra o PDF.** Todas as respostas batem com o texto
      extraído por página. Ygor Alves / UFPB → página 2 ✔ · coworking em João
      Pessoa → página 3 ✔ · `contato@yaitec.com` → página 3 ✔ · StartStak →
      página 2 ✔ · "2026" → página 1 ✔. Reli as 14 respostas da conversa longa:
      **nenhuma afirmação sem respaldo no documento**
- [ok] Nenhuma pergunta fundamentada voltou sem citação
- [estranho] **As citações são quase sempre as mesmas cinco.** Com
      `RETRIEVAL_TOP_K=5` num documento de 10 chunks, metade do documento passa
      do limiar em quase toda pergunta — e o primeiro chip costuma ser o
      cabeçalho da página 1, sem relação com a pergunta. O texto do diálogo já
      protege isso ("trechos consultados … nem todo trecho aparece na resposta"),
      mas numa demonstração o primeiro chip que o avaliador clicar tende a abrir
      um trecho irrelevante

---

## 3. Pergunta de continuação

- [ok] `Quem fundou a YAITEC?` → *"fundada por Ygor Alves … engenheiro
      eletricista formado pela UFPB"*
- [ok] `e a formação dele?` → *"Ygor Alves é engenheiro eletricista, formado
      pela UFPB (página 2)"*. Log: `{"event":"chat.condensed","used_llm":true,"fallback":false}`
- [ok] `Onde o time se reúne?` → coworking em João Pessoa, página 3
- [ok] `e quem mora longe de lá?` → *"Quem reside fora de João Pessoa trabalha
      de forma 100% remota (página 3)"*. Condensação com LLM em 813 ms
- [ok] A citação da segunda pergunta aponta para a página 3

A condensação é o que está segurando esse bloco, e ela funciona.

---

## 4. Recusa

- [ok] `Qual a receita do bolo de cenoura?` → *"Não encontrei essa informação no
      documento enviado. Tente reformular a pergunta…"*
  - [ok] aparece como mensagem normal do assistente, com a marca discreta
        "sem base no documento". Zero toasts na tela
  - [ok] nenhuma área de citações renderizada
  - [ok] **vem rápido e sem chamar o modelo**: 0,82 s do Enter ao texto na tela.
        No log, `chat.retrieved` (`above_threshold: 0`, `top_score: 0.527`) →
        `chat.refused`, e **nenhum** `chat.generated`
- [ok] `Quantos gols o Pelé marcou?` → idêntico (`top_score: 0.497`)
- [ok] **Fronteira do limiar** — `A YAITEC faz consultoria tributária?` passou do
      limiar (`above_threshold: 5`) e foi para o modelo, que respondeu:
      *"Não encontrei essa informação no documento. O texto menciona que a
      YAITEC oferece consultoria de IA (página 1 e página 3), mas não faz
      referência a serviços de consultoria tributária."*
      Recusou sem inventar, e ainda explicou a diferença. É o melhor
      comportamento possível nesse caso, e vale mostrar na demonstração

---

## 5. Busca por termo exato

Confirmando a leitura do roteiro: em pergunta escrita por extenso quem responde
é a busca densa. A observação abaixo é o dado que faltava para a `B.5`.

Grupo A (pergunta em linguagem natural):

- [ok] `Qual o e-mail de contato?` → `contato@yaitec.com`, citação na **página 3**
- [ok] `O que é a UFPB no documento?` → instituição onde Ygor Alves se formou
- [ok] `A YAITEC trabalha com a StartStak?` → sim, cliente/parceira, página 2

Grupo B (termo sozinho):

- [ok] `contato@yaitec.com` → mesma resposta, mesma página
- [ok] `UFPB` → *"Universidade Federal da Paraíba"* (expansão que só o modelo
      podia dar; o documento traz apenas a sigla)
- [ok] `StartStak` → cliente e parceira, página 2

**Os dois grupos diferem, mas não no que importa.** O conteúdo das respostas é
equivalente nos três pares; o que muda é **o conjunto de trechos citados**:

| termo | citações no grupo A | citações no grupo B |
|---|---|---|
| `contato@yaitec.com` | 1, 1, 2, 3, 3 | 1, 2, 2, 3, 3 |
| `UFPB` | 1, 1, 2, 2, 2 | 1, 2, 2, 3, 3 |
| `StartStak` | 1, 1, 2, 2, 3 | 1, 1, 2, 2, 2 |

Ou seja: a fusão mexe no ranking quando o termo entra sozinho, e não mexe na
resposta final. **Para o README: descrever a via lexical como um reforço de
ranking em consulta por termo, não como o que sustenta a resposta.**

- [estranho] **A condensação estourou o timeout uma vez.** Na pergunta
      `StartStak`: `{"event":"chat.condensed","used_llm":false,"fallback":true,"duration_ms":5001}`
      — os 5 s cheios de `CONDENSE_TIMEOUT_SECONDS`, e o turno inteiro levou
      8,9 s. O fallback fez o certo (seguiu com a pergunta crua e a resposta
      saiu correta), mas são 5 segundos parados numa pergunta de uma palavra

---

## 6. Erros e limites

- [ok] **Quota** — não deu para estourar de verdade: 12 requisições em paralelo
      contra a API passaram todas, e as ~45 perguntas do roteiro inteiro não
      atingiram limite nenhum. O caminho foi verificado injetando o evento
      `error` com `code: limite_de_uso` no stream:
  - [ok] aviso claro: *"Limite de uso atingido … Pode ser o limite por minuto ou
        o limite diário do plano gratuito."*
  - [ok] com ação **"Tentar de novo"**
  - [ok] **a pergunta digitada não se perde** — volta inteira para o campo
  - [ok] **"tentar de novo" não duplica a pergunta** — a conversa fica com uma
        pergunta e uma resposta; o balão órfão é removido quando a falha
        acontece antes do primeiro token
- [ok] Pergunta vazia ou só espaços → botão desabilitado, e `Enter` não envia
- [falhou] **Texto de 3.000 caracteres recebe a mensagem errada.** O servidor
      devolve `422` (o teto é 2.000, `schemas.py:76`) e a tela mostra:
      *"Arquivo não é um PDF válido — O conteúdo enviado não abre como PDF.
      Confira se o arquivo abre no seu leitor e envie de novo."*
      A pessoa colou **texto numa pergunta** e recebeu instruções sobre **abrir
      um arquivo**. Nada quebra e a pergunta não se perde, mas a mensagem manda
      para o lugar errado.
      Origem: `backend/app/errors.py:122` mapeia `422 → InvalidFileError.code`
      (`arquivo_invalido`), e `frontend/src/lib/errors.ts` traduz esse código
      como problema de PDF. Falta um código para "pergunta inválida"

---

## 7. Interrupção e recuperação

- [ok] Cancelar no meio → o botão "Parar resposta" aparece durante o stream,
      o cancelamento para de verdade, a UI volta usável e o que chegou fica
      marcado *"Resposta interrompida antes do fim."*
- [ok] **F5 no meio de um streaming** → histórico volta completo (4 → 6
      mensagens) e a resposta interrompida aparece marcada. No banco,
      `truncated = true` (3 mensagens truncadas registradas na sessão)
- [ok] F5 no meio não cria conversa nova — mesmo `conversationId` antes e depois
- [ok] F5 com a conversa parada → documento e histórico restaurados, sem
      conversa nova
- [ok] Rede desligada → *"Sem resposta do servidor — Não foi possível falar com
      a aplicação. Verifique sua conexão e tente de novo."* com ação de repetir.
      Sem tela branca, e a pergunta continua no campo
- [ok] Religar e continuar → volta a funcionar sem recarregar

---

## 8. Teclado e leitura (NFR-10)

- [ok] Percurso de `Tab`: pular para o conteúdo → link do rodapé → tema →
      enviar outro documento → cada chip de citação → campo de pergunta →
      botão de enviar. O botão de enviar só entra no percurso quando há texto —
      com o campo vazio ele está `disabled`, que é o correto
- [ok] `Enter` envia · `Shift+Enter` quebra linha
- [ok] Chip acionado por teclado abre o trecho, e `Esc` devolve o foco ao chip
- [ok] Foco visível em tudo que recebe foco — anel de 3 px
      (`box-shadow: oklab(0.71 … / 0.5) 0 0 0 3px`). Chega com 150 ms de
      transição; medir antes disso dá falso negativo
- [ok] **Contraste nos dois temas.** Medindo cada texto renderizado contra o
      fundo composto: escuro — 15 textos, pior razão **7,37:1**; claro — 15
      textos, pior razão **4,26:1** (num título de 21 px, cujo mínimo é 3:1).
      Nenhum reprovado no AA

---

## 9. Conversa longa

- [ok] 10 perguntas na mesma conversa → 20 mensagens, ordem
      pergunta/resposta alternada, sem balão vazio, sem duplicata, sem resposta
      interrompida no meio
- [falhou] **A rolagem quebra quando a conversa passa da altura da tela.**
      Com 22 mensagens, numa janela de 900 px:

      viewport da conversa   scrollHeight 4059 = clientHeight 4059  → não rola
      página                 scrollHeight 4356 vs 900               → rola a página
      campo de pergunta      y = 3823                               → fora da tela

      Três consequências, todas visíveis numa demonstração:
      1. a conversa **abre no topo**, na primeira pergunta, e não na última
         resposta;
      2. o acompanhamento do fim (`useStickToBottom`) fica inerte — ele escreve
         `scrollTop` num elemento que não tem transbordo;
      3. **o campo de pergunta sai da tela**, e é preciso rolar a página inteira
         para perguntar de novo — exatamente o que o comentário do `ChatView`
         diz que a altura fixa existe para evitar.

      Causa isolada no navegador: `AppShell.tsx:138` usa
      `grid min-h-dvh grid-rows-[auto_1fr_auto]`. Com `min-h-dvh` a linha `1fr`
      cresce além da viewport, então o `h-full` do `ChatView` resolve para a
      altura crescida e o `ScrollArea` nunca transborda. Forçando
      `height: 100dvh` no mesmo elemento, ao vivo: `clientHeight` volta a 603,
      a página volta a 900 e o campo volta a ficar visível.
- [ok] Subir para reler **não** arrasta de volta para baixo (verificado; e
      continua valendo depois da correção da altura)
- [ok] Nada estranho no meio da conversa

---

## 10. Olhar de avaliador

- [ok] **Reli a conversa inteira.** Nenhuma resposta parece inventada. Confronto
      por página: todas as atribuições de página conferem com o texto extraído,
      inclusive as compostas ("páginas 1 e 3"). A única informação que não está
      no documento é a expansão de `UFPB` para "Universidade Federal da
      Paraíba" — conhecimento do modelo, não citado como se fosse do PDF
- [ok] `docker compose logs backend | grep -i "AIza"` → **vazio**.
      Fui além: a chave real de 53 caracteres não aparece em nenhum log de
      nenhum serviço (0 ocorrências), nem fragmentos de 12 caracteres dela,
      nem no bundle servido pelo nginx. `GET /api/config` publica só
      `max_upload_mb`, `max_pdf_pages`, `max_extracted_chars`
- [ok] Nenhuma mensagem técnica vazou. Testei os caminhos que costumam vazar:
      documento inexistente → *"Documento não encontrado — Este documento não
      existe mais no servidor."*; API respondendo `500` → *"Algo deu errado no
      servidor"*. Sem stack trace, sem nome de exceção, sem status HTTP na tela
- [ok] Todo texto de interface em pt-BR, nas duas telas, incluindo os rótulos
      de leitor de tela

---

## Logs — verificação à parte

Existem, e são bons. `structlog` emitindo **uma linha JSON por evento** em
stdout (`logging_setup.py`), capturada pelo driver do Docker.

- `request_id` amarrado uma vez no middleware e herdado por tudo que a
  requisição dispara, **inclusive a task de background** da ingestão: um
  `grep` por id devolve a ingestão inteira, de `document.received` a
  `document.ready`
- `document_id` amarrado no início do pipeline, pelo mesmo motivo
- Devolvido ao cliente no header `X-Request-Id` — dá para ligar o que apareceu
  na tela à linha exata do log
- Eventos observados na prática: `app.started`, `document.received`,
  `document.extracted`, `document.chunked`, `embedding.batch` (nível debug, um
  por lote), `document.ready`, `document.duplicate`, `document.retry`,
  `document.failed`, `conversation.created`, `chat.turn_started`,
  `chat.condensed` (com `used_llm` e `fallback`), `chat.retrieved` (com
  `candidates`, `above_threshold`, `top_score`), `chat.refused`,
  `chat.generated` (com `token_count`, `truncated`), `request.failed`
- Redação de segredo na borda de renderização, **depois** do `format_exc_info` —
  cobre traceback, que é onde uma chave costuma escapar. Confirmado sem
  vazamento

Uma lacuna, pequena mas real:

- **Turno interrompido não deixa evento de fecho.** Quando o cliente cancela ou
  dá F5 no meio do stream, o log tem `chat.turn_started` e `chat.retrieved` e
  mais nada — nem `chat.generated`, nem `chat.client_disconnected`. Este último
  tem **zero** ocorrências em toda a sessão: o gerador é fechado por
  `GeneratorExit` no `yield`, então o laço nunca chega à volta seguinte onde o
  `is_disconnected()` seria consultado. A persistência não sofre (o `finally`
  roda e grava `truncated = true`, confirmado no banco), mas quem lê o log vê um
  turno que começa e nunca termina — parecido demais com uma requisição travada

---

## Banco

- Tabelas: `documents`, `chunks`, `conversations`, `messages`
- 180 chunks, **todos** com embedding de 768 dimensões, nenhum nulo
- Índices presentes: `chunks_embedding_idx` (pgvector), `chunks_tsv_idx`
  (busca lexical), `messages_conversation_id_created_at_idx`,
  `conversations_document_id_idx` e a única
  `documents_session_id_content_hash_key` que sustenta a deduplicação por sessão
- `truncated` gravado corretamente nas 3 respostas interrompidas

---

## Encaminhamento

Nada disso se conserta dentro da `B.5`. Como está registrado na spec:

| # | O quê | Onde | Peso |
|---|---|---|---|
| 1 | Conversa longa não rola por dentro; campo de pergunta sai da tela | `AppShell.tsx:138` | **alto** — aparece em qualquer demonstração que passe de ~8 mensagens |
| 2 | `422` de pergunta longa vira mensagem sobre PDF | `errors.py:122` + `lib/errors.ts` | médio |
| 3 | Barra de progresso não avança no PDF de exemplo | `EMBEDDING_BATCH_SIZE` / `ingestion.py:141` | médio — é o arquivo da demo |
| 4 | Turno interrompido sem evento de fecho no log | `chat.py:296-317` | baixo |
| 5 | Chips de citação quase constantes (TOP_K=5 sobre 10 chunks) | retrieval / limiar | baixo — é decisão de produto, não defeito |

Os itens 1 e 2 são `/bugfix`. O 3 e o 5 são rework da fase dona (ou decisão
consciente registrada no README). O 4 é observabilidade e pode esperar.
