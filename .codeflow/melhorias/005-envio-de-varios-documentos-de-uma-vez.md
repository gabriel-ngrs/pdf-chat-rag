---
id: MELH-005
titulo: "Arrastar e soltar vários documentos de uma vez"
solicitado_em: 2026-08-18
solicitado_por: owner
tipo: funcionalidade / fluxo de envio
area: frontend + backend + dados
prioridade: média
esforco: médio (escopo A) · alto (escopo B)
status: aberto — análise de custo entregue, escopo pendente de decisão do owner
fase_dona: nenhuma (exige spec própria)
---

# MELH-005 — Enviar vários PDFs de uma vez

## O pedido

Poder arrastar e soltar mais de um documento no sistema, em vez de um por vez.

## A pergunta que decide o custo

"Vários documentos" tem duas leituras, e elas custam coisas muito diferentes:

**Escopo A — envio em lote, conversa com um por vez.** A pessoa solta cinco
PDFs, os cinco são processados, e ela escolhe com qual conversar. Cada conversa
continua sendo sobre um documento só. É uma mudança de fluxo de envio.

**Escopo B — conversa sobre vários ao mesmo tempo.** A pergunta é respondida com
trechos de qualquer um dos documentos enviados, e a citação precisa dizer de
qual arquivo veio. É uma mudança no modelo de dados, no retrieval, no prompt e
na citação — ou seja, no eixo central do escopo.

O resto deste documento mede as duas. **Elas não são degraus da mesma escada:**
o escopo A não é "metade do B". O A pode ser entregue sozinho e continuar
correto; o B, se vier depois, aproveita a interface do A mas refaz o miolo.

## O que existe hoje

O sistema inteiro é "um documento, uma conversa", e isso está escrito em oito
lugares, não em um:

| Onde | O que amarra |
|---|---|
| `db/002_chat.sql:45` | `conversations.document_id uuid NOT NULL` — a conversa aponta para **um** documento |
| `backend/app/adapters/repository.py:123` | `WHERE document_id = $1` na busca densa |
| `backend/app/adapters/repository.py:162` | `WHERE document_id = $1` na busca lexical |
| `backend/app/core/retrieval.py:127` | chunks são identificados por `chunk_index` na fusão RRF — único **dentro** de um documento |
| `backend/app/core/prompt.py:21` | `<<<TRECHO {index} | pagina {page}>>>` — o rótulo carrega página, não arquivo |
| `backend/app/core/models.py:71` | `Citation` tem página, trecho e score; não tem documento |
| `frontend/src/App.tsx:19` | `localStorage['talkdoc:document-id']` — uma string, um documento |
| `frontend/src/components/ChatView.tsx:22` | `talkdoc:conversation` guarda o par documento↔conversa |

E o envio, especificamente:

- `UploadDropzone.tsx:31` — `useState<File | null>`, um arquivo;
- `UploadDropzone.tsx:63` — `event.dataTransfer.files[0]`, o primeiro e só ele;
- `UploadDropzone.tsx:142` — o `<input type="file">` **não** tem `multiple`;
- `useUpload.ts:69` — `send(file: File)`, uma requisição, um arquivo;
- `useDocumentStatus.ts:49` — acompanha **um** `documentId` por vez;
- `ProcessingStatus.tsx` — desenha o progresso de um documento.

Vale registrar que isso não é acidente: a `FEAT-0003` (biblioteca de
documentos) foi **cortada de propósito** em
[`decisions/2026-08-17-revisao-adversarial-das-specs.md`](../decisions/2026-08-17-revisao-adversarial-das-specs.md),
decisão 1. Os motivos de lá continuam valendo em parte (o enunciado
pede "envia um PDF", singular) e em parte não (dois dos bugs que a cortaram —
excluir documento em `processing` e trocar de documento com SSE em andamento —
são de exclusão e troca, que não são o que este pedido traz).

---

## Escopo A — envio em lote, uma conversa por documento

### O que muda

**Frontend, e quase só ele.**

1. `UploadDropzone` — `multiple` no input, `dataTransfer.files` inteiro em vez
   de `[0]`, `File | null` vira `File[]`, e a área tracejada passa a mostrar
   uma lista com nome, tamanho e estado de cada arquivo, com remoção
   individual. É a maior parte do trabalho de interface, e onde o desenho
   precisa de cuidado: **um envio de lote falha em partes**, e a tela tem que
   dizer quais três deram certo e por que os outros dois não.
2. `validateSelection` já serve por arquivo, sem mudança. O que falta é a regra
   do conjunto: um teto de arquivos por lote (sugestão: 10) e a recusa de dois
   arquivos idênticos dentro do mesmo arrasto — hoje o servidor dedupa por
   `(session_id, content_hash)`, mas dois envios simultâneos do mesmo PDF
   correm um contra o outro na `UNIQUE`.
3. `useUpload.send` vira `sendMany`, **uma requisição por arquivo**, em série ou
   com concorrência baixa. Isso é recomendação, não detalhe: mandar N arquivos
   num único `POST` esbarraria em `documents.py:66`, onde
   `_reject_by_declared_size` recusa pelo `Content-Length` do corpo inteiro — o
   limite de 25 MB passaria a valer para a **soma** do lote, e a mensagem de
   erro diria "o arquivo excede o limite" sobre um arquivo que não excede.
4. `App.tsx` — `documentId: string | null` vira lista, mais o id selecionado
   para conversa. A chave do `localStorage` muda de forma, então precisa de
   leitura tolerante ao valor antigo (uma string crua) ou de chave nova.
5. Acompanhamento — `useDocumentStatus` acompanha um id. Para N, ou se instancia
   N vezes (5 documentos = 5 requisições a cada 1,5 s) ou se acompanha em lote.
   Com teto de 10 o custo bruto é tolerável, mas a segunda opção é mais limpa e
   é o único pedaço de backend do escopo A: `GET /api/documents?ids=…`
   devolvendo a lista de estados. ~30 linhas mais testes.
6. Tela nova, pequena: escolher com qual documento conversar, e voltar para essa
   escolha a partir do chat. Hoje "Enviar outro documento" descarta tudo
   (`App.tsx:158`); com lote, descartar tudo deixa de ser a única saída.

**Backend: nada obrigatório.** `POST /api/documents` já aceita um arquivo por
requisição e responde `202` na hora; N requisições funcionam sem alterar uma
linha. O que muda é o regime de execução, e isso é a próxima seção.

### O custo em números

| Item | Estimativa |
|---|---|
| `UploadDropzone` (lista, estados por arquivo, remoção, erros parciais) | 3–4 h |
| `useUpload` → envio de lote, com limite de concorrência | 1 h |
| `App.tsx` + seleção de documento + `localStorage` com migração | 2 h |
| Acompanhamento de N (`GET /api/documents?ids=`, front e back) | 1,5–2 h |
| Testes: os 5 arquivos existentes de teste de envio e status | 2–3 h |
| README e documentação de limitação | 0,5 h |
| **Total** | **10–13 h** |

Nenhuma dependência nova. Nenhuma alteração de banco. Nenhum contrato quebrado
— só um endpoint acrescentado.

---

## Escopo B — conversar com vários documentos ao mesmo tempo

### O que muda

**Banco.** `conversations.document_id` (um uuid, `NOT NULL`) precisa virar
relação N:N — uma tabela `conversation_documents`. E aqui mora uma armadilha do
projeto: os arquivos de `db/` **rodam uma vez só, em banco vazio**
(`db/001_init.sql:1`). Não há ferramenta de migração. Em desenvolvimento a
mudança custa `make down` e reingestão de tudo; se já houvesse ambiente com
dado real, custaria um plano de migração que o projeto não tem.

**Retrieval.** As duas queries passam a filtrar por lista
(`= ANY($1::uuid[])`), o que é trivial de escrever e não é trivial de acertar:

- **Recall.** O comentário de `repository.py:127-133` explica que o HNSW
  devolve os vizinhos **globais** e só depois aplica o `WHERE document_id`. Com
  a varredura iterativa ligada isso se resolve para um documento; para N, o
  mesmo `LIMIT 5` passa a ser disputado por N corpora, e o documento que
  responde a pergunta pode não colocar nenhum trecho no top-5. Ou `top_k`
  cresce (mais tokens, mais latência, mais quota) ou se busca `k` por documento
  e funde depois. Qualquer dos dois exige medir, não supor.
- **Colisão de identidade na fusão.** `core/retrieval.py:127` diz, com todas as
  letras: *"Chunks são identificados por `chunk_index`, que é único no
  documento — a busca é sempre filtrada por um documento só."* Com dois
  documentos no mesmo resultado, o `chunk_index` 3 do PDF A e o 3 do PDF B são
  a mesma chave para o RRF: ele fundiria dois trechos diferentes num só. É um
  bug silencioso — sem exceção, sem log, com citação apontando para a página
  errada do arquivo errado. A chave precisa virar `(document_id, chunk_index)`.
- **Limiar.** `similarity_threshold = 0.561` foi calibrado na fase A.5 contra a
  distribuição de cossenos de **um** documento. Ele não é obviamente inválido
  para N, mas também não é obviamente válido — e é ele que decide entre
  responder e recusar (o [BUG-002](../bugs/002-limiar-de-similaridade-recusa-perguntas-legitimas.md)
  já mostrou o que acontece quando esse número está errado).

**Citação.** Hoje a `Citation` não tem documento (`core/models.py:71`), e a
instrução do prompt manda o modelo citar **só a página**
(`core/prompt.py:44`) — regra que veio do
[BUG-005](../bugs/005-resposta-cita-trecho-n-que-nao-existe-na-interface.md).
Com vários documentos, "página 7" deixa de identificar coisa alguma. Precisam
mudar, na mesma passada: `Citation`, o `CHUNK_OPEN_TEMPLATE`, as
`ANSWER_INSTRUCTIONS`, o payload SSE, `types.ts`, o `CitationChip` e os testes
de prompt que prendem o texto atual.

**Eval.** `backend/eval/dataset.json` é de um documento. Cross-documento sem
caso de eval é alegação sem prova, e o eval é entregável citado no README.

**Interface.** Quais documentos estão na conversa, como se tira um, e o que
acontece com o histórico quando o conjunto muda no meio.

### O custo em números

| Item | Estimativa |
|---|---|
| `db/003` + repositório + reingestão do ambiente | 2–3 h |
| Retrieval multi-documento: chave do RRF, `k` por documento, recall | 4–6 h |
| Calibração do limiar com o eval e novos casos no dataset | 3–4 h |
| `Citation` com documento: modelo, SSE, prompt, front, testes | 4–5 h |
| Interface da conversa multi-documento | 3–4 h |
| **Total, sobre o escopo A já pronto** | **16–22 h** |

---

## O que trava de verdade, nos dois escopos

Três coisas, e nenhuma delas é código de interface.

### 1. A quota do Gemini, que é diária

`ingestion.py:33` tem um semáforo de **uma ingestão por vez**, e o comentário
diz por quê: *"duas em paralelo cairiam ambas em 429, porque o limite de tokens
por minuto do free tier é do projeto, não da requisição"* (NFR-8). Enviar cinco
PDFs não os processa em paralelo — os enfileira. Cinco documentos no teto da
spec (20 páginas) são minutos de espera, com a tela mostrando fila.

Pior que a espera: o [BUG-004](../bugs/004-mensagem-de-quota-promete-um-minuto-mas-o-limite-e-diario.md)
registrou que **o limite que dói é o diário**, não o por minuto. Envio em lote
multiplica por N o consumo de quota por gesto do usuário. Um arrasto
desatento de dez PDFs pode gastar a quota do dia inteiro do projeto — e a
mensagem de erro que aparece hoje é a de um documento só falhando.

**Consequência para o escopo A:** o teto de arquivos por lote não é
enfeite de interface, é controle de quota. E a fila precisa ser visível, com
posição, senão o segundo documento parece travado enquanto o primeiro processa.

### 2. A fila não sobrevive a um restart

O processamento é agendado por `BackgroundTasks` do FastAPI
(`documents.py:156`): roda no mesmo processo, depois da resposta, em memória.
Com um documento a janela de risco é curta. Com dez enfileirados atrás de um
semáforo, uma reinicialização do container derruba o que ainda não rodou, e os
documentos ficam `pending` para sempre — o `sweep_orphans` do startup
(`main.py:77`) varre órfãos, mas varrer é marcar como falho, não retomar.

Isso é aceitável para um lote pequeno com a falha visível na tela e um botão de
reenviar. Deixa de ser aceitável se o lote crescer, e aí a resposta é fila
persistida — que é outro projeto, não esta melhoria.

### 3. O limite de tamanho é por requisição

`_reject_by_declared_size` (`documents.py:66`) mede o `Content-Length` do corpo.
Mantendo **um arquivo por requisição**, o limite de 25 MB continua significando
o que significa hoje e nada precisa mudar. Essa é a razão técnica de a
recomendação ser N requisições, e não um multipart com N campos.

---

## Recomendação

**Fazer o escopo A. Não fazer o escopo B agora.**

O escopo A entrega o que foi pedido literalmente — arrastar vários arquivos —,
custa 10–13 h, não toca em banco, não toca em retrieval e não arrisca o eixo de
fundamentação, que é o mais pesado na avaliação. O que ele exige de cuidado é
produto, não arquitetura: fila visível, teto de arquivos, erro por arquivo.

O escopo B custa o dobro e mexe exatamente onde o sistema é forte hoje: citação
exata, limiar calibrado, fusão RRF testada. A colisão de `chunk_index` na fusão
é o tipo de defeito que passa em toda a suíte atual e só aparece como "a
resposta citou a página errada" — o pior sintoma possível neste produto. Se o
escopo B for adiante um dia, ele merece spec própria e eval antes do código,
não um puxadinho.

Se o objetivo for demonstrar capacidade de conversar com um acervo, existe um
meio-termo mais barato que o B: manter uma conversa por documento e oferecer
troca rápida entre documentos já processados, sem descartar as conversas — cabe
dentro do escopo A por mais ~2 h, e não toca em nada do retrieval.

## Critérios de aceite (escopo A)

- [ ] Arrastar cinco PDFs de uma vez cria cinco documentos, e a tela mostra o
      estado de cada um por nome de arquivo.
- [ ] Um arquivo inválido no meio do lote é recusado sozinho, com a razão, e os
      demais seguem.
- [ ] O mesmo PDF arrastado duas vezes no mesmo lote é enviado uma vez só.
- [ ] Há teto de arquivos por lote, com mensagem própria ao ser ultrapassado.
- [ ] A fila é visível: quem está sendo lido agora e quantos esperam.
- [ ] Recarregar a página no meio do lote não perde o acompanhamento dos
      documentos já aceitos.
- [ ] O limite de tamanho continua sendo por arquivo, não pela soma do lote.
- [ ] Cada conversa continua sendo sobre um documento só, e a citação continua
      exata (nenhuma alteração em `retrieval`, `prompt` ou `Citation`).
- [ ] `make check` verde.

## Restrições do projeto que valem aqui

- Cor **sempre** por token semântico; texto de interface em pt-BR.
- `tsc --strict` sobre `frontend/src`, sem `any`.
- Dependência nova passa por `npm audit --audit-level=high` — e este trabalho
  não precisa de nenhuma.
- `prefers-reduced-motion` respeitado na lista de arquivos e na fila.
- Nenhum caminho pode deixar documento preso em `processing`
  (regra de `ingestion.py`), e isso vale para cada item do lote.

## Relacionado

- [`decisions/2026-08-17-revisao-adversarial-das-specs.md`](../decisions/2026-08-17-revisao-adversarial-das-specs.md)
  — decisão 1, que cortou a biblioteca de documentos e explica o que ela
  trazia junto.
- [BUG-004](../bugs/004-mensagem-de-quota-promete-um-minuto-mas-o-limite-e-diario.md)
  — a quota que dói é a diária; é ela que o envio em lote multiplica.
- [BUG-008](../bugs/008-barra-de-progresso-nao-avanca-no-pdf-de-exemplo.md)
  — progresso de um documento; com fila, o mesmo indicador passa a ter que
  distinguir "esperando" de "lendo".
