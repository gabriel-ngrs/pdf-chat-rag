---
versão: 1.0
status: estável
atualizado: 2026-08-17
data: 2026-08-17
workflow: create-spec
tags: [escopo, rag, embeddings, infra, entrega]
status_decisão: ativa
supersede: null
relaciona-com: []
---

# Decisões: revisão adversarial das specs — cortes de escopo e contratos fixados

## Contexto

As três specs (`FEAT-0001` ingestão, `FEAT-0002` chat com RAG, `FEAT-0003` biblioteca) foram submetidas a cinco revisores adversariais em paralelo: um crítico por spec, um de coerência cruzada e um simulando o avaliador da YAITEC. Os revisores encontraram seis defeitos de infraestrutura no esqueleto do `/bootstrap` — vários verificados empiricamente, rodando nginx, `pg_isready` e `uv` — capazes de derrubar o `docker compose up` do avaliador, que é o único critério binário do desafio.

Quatro revisores independentes apontaram o mesmo bug de roteamento no nginx; três apontaram que o README, entregável literal do enunciado, não tinha dono em nenhuma das 27 fases planejadas. O orçamento também não fechava: 27 fases com gate próprio, para 30h corridas num desafio estimado em 8h.

Estas decisões consolidam os cortes e fixam os contratos que estavam em aberto.

## Decisões tomadas

### 1. Cortar a `FEAT-0003` (biblioteca de documentos) do plano de execução

**Por quê:** não pontua em nenhum dos três eixos avaliados (o enunciado pede "envia um PDF e faz perguntas sobre o conteúdo dele", singular) e não é neutra: o `003_library_indexes.sql` precisava declarar os `ON DELETE CASCADE` ausentes nas tabelas anteriores, e como o Postgres não tem `ADD CONSTRAINT IF NOT EXISTS` e o `docker-entrypoint-initdb.d` para no primeiro erro, uma spec opcional podia impedir o banco de inicializar. Somam-se dois bugs que ela introduzia: excluir documento em `processing` colide com o `BackgroundTasks` da ingestão, e trocar de documento com stream SSE em andamento anexa tokens do documento A sob o documento B — citação da página errada, no app cujo eixo mais pesado é fundamentação. As ~5h liberadas vão para eval honesto, README e demo, que movem os três eixos e são entregáveis do enunciado.

**Alternativa rejeitada:** manter como P2 opcional. Rejeitada porque uma spec P2 não tem custo zero — cria pressão para executar "só o A.1", que era justamente a fase que alterava constraint.

**Implicações:** a dor que a motivava (recarregar a página e perder o documento) é resolvida em `FEAT-0002` persistindo `documentId` e `conversationId` em `localStorage`. Os `ON DELETE CASCADE` passam a ser declarados por quem cria as tabelas. `session_id` permanece como coluna nas tabelas.

### 2. Fixar o contrato de embedding na spec, antes da primeira fase

**Por quê:** `gemini-embedding-001` devolve 3072 dimensões por default e o índice HNSW do pgvector aceita no máximo 2000 — o `CREATE INDEX` abortaria dentro do `docker-entrypoint-initdb.d`, derrubando o compose a frio. Verificou-se também que `USING hnsw (embedding)` sem opclass sequer compila (`no default operator class`), e que um índice L2 não atende o `ORDER BY embedding <=> $1` de cosseno. Contrato fixado: `gemini-embedding-001`, `output_dimensionality=768`, normalização L2 manual (obrigatória quando a dimensão difere de 3072), `task_type` assimétrico (`RETRIEVAL_DOCUMENT` para chunks, `RETRIEVAL_QUERY` para a pergunta), coluna `vector(768)` e índice `USING hnsw (embedding vector_cosine_ops)`.

**Alternativa rejeitada:** manter como Open Question a resolver na fase `A.4`, como estava. Rejeitada porque o custo de descobrir tarde é `make down -v`, reingestão e quota queimada — os scripts de `db/` só rodam em banco vazio.

**Implicações:** `EMBEDDING_DIM` sai da lista de "configurável por env" — um `.sql` estático não interpola variável. O lifespan valida a coerência entre a dimensão da coluna e a configuração, falhando rápido.

### 3. Chunking por página, sem cruzar fronteira

**Por quê:** com a janela deslizante de 1000 caracteres, um chunk que cruza a fronteira de página recebia o número da página do seu início — citação errada num PDF que o avaliador confere à mão. Além disso o critério de aceite antigo era falso por construção: overlap exato de 150 caracteres e corte em fronteira de parágrafo são incompatíveis. Chunking por página com `CHUNK_SIZE=500` torna a citação exata por construção e produz ~10 chunks no PDF de exemplo em vez de ~4.

**Alternativa rejeitada:** janela deslizante contínua sobre o documento inteiro, com o número da página do início do chunk. Rejeitada por produzir citação incorreta justamente no eixo avaliado.

**Implicações:** com ~10 chunks e `RETRIEVAL_TOP_K=5`, o retrieval passa a selecionar de fato — antes recuperava o documento inteiro e o `recall@5` era 1,0 por construção.

### 4. Cortar o pool de chaves Gemini

**Por quê:** a própria spec registrava que os limites do free tier são por projeto, e não por chave — ou seja, o recurso não fazia nada com as chaves que o candidato tem. Custava código de round-robin, detecção de `429` por chave, um critério de aceite, um teste, uma variável de ambiente e um parágrafo de documentação, sem pontuar em eixo nenhum.

**Alternativa rejeitada:** manter como recurso opcional. Rejeitada por ser complexidade que a própria documentação declarava inoperante.

### 5. Cortar a checagem de autorização por sessão, mantendo a coluna

**Por quê:** o desafio não tem autenticação nem multiusuário. Sem biblioteca e sem rota de listagem — ambas cortadas com a decisão 1 —, vazar o estado de um documento por UUID é irrelevante, e a rota destrutiva que tornava isso grave saiu junto. Manter a checagem arrastaria uma dimensão de autorização por endpoint, com testes, sem pontuar.

**Alternativa rejeitada:** filtrar por `session_id` em toda rota, como exigia a `FEAT-0003`. Rejeitada junto com a spec que a motivava.

**Implicações:** `session_id` continua sendo gravado e é registrado no README como organização, não como fronteira de segurança.

### 6. Usar o SSE nativo do FastAPI

**Por quê:** verificado no ambiente do projeto (FastAPI 0.141.1 resolvido no `uv.lock`): `fastapi.sse.EventSourceResponse` existe, funciona em `POST`, e já define `Content-Type`, `Cache-Control: no-cache`, `X-Accel-Buffering: no` e keep-alive a cada 15 s. A spec anterior mandava usar `StreamingResponse` sem especificar um único header, e o formato do frame SSE seria reinventado à mão, com risco de divergir do parser do frontend.

**Alternativa rejeitada:** `StreamingResponse` com os headers listados nominalmente na spec. Rejeitada por ser trabalho manual para replicar o que a biblioteca já entrega.

**Implicações:** o floor de dependência sobe para `fastapi>=0.135`. `GZipMiddleware` fica proibido — quebra SSE.

### 7. Incluir busca híbrida (densa + full-text, fundidas por RRF) como fase final opcional

**Por quê:** num corpus de poucas páginas a busca densa borra termos exatos — nome próprio, e-mail, telefone —, que é exatamente o que um avaliador pergunta. A fusão RRF vive em `core/retrieval.py`, é pura, cabe em ~20 linhas e é testável offline; é a peça que melhor sustenta a alegação de "RAG artesanal, sem framework" da constitution.

**Alternativa rejeitada:** MMR/diversidade e expansão multi-query. A primeira é no-op num corpus pequeno; a segunda gasta chamada extra de LLM no teto de ~10 RPM que a condensação já estrangula.

**Implicações:** entra como última fase da `FEAT-0002`, executada só se as anteriores fecharem com folga.

### 8. Criar uma fase P0 de README e demonstração

**Por quê:** três revisores independentes notaram que o README não era objetivo, arquivo alterado nem gate de nenhuma das 27 fases — sendo entregável literal do enunciado ("README com decisões de arquitetura e quais ferramentas de IA você usou") e o artefato onde o avaliador lê as decisões de RAG que sustentam o eixo mais pesado.

**Alternativa rejeitada:** tratar o README como item de checklist na Definition of Done, como estava. Rejeitada porque item de checklist sem fase dona é o que sempre sobra para os últimos vinte minutos.

**Implicações:** a fase inclui a tabela de decisões, as limitações conhecidas, a seção de ferramentas de IA, um exemplo de uso reproduzível e uma demonstração gravada.

### 9. Manter o `.codeflow/` no repositório entregue, com um parágrafo explicativo no README

**Por quê:** decisão do owner. O avaliador simulado marcou o volume de planejamento como possível sinal de texto gerado sem entendimento, especialmente por as specs citarem arquivos do framework que não estão no repositório. Um parágrafo explicando que é um framework pessoal de planejamento, mais as decisões defendidas com as próprias palavras no README, converte o sinal de suspeita em diferencial.

**Alternativa rejeitada:** remover o `.codeflow/` da entrega. Rejeitada pelo owner.

## Próximos passos sugeridos

- Reescrever `FEAT-0001` e `FEAT-0002` incorporando estas decisões e os demais achados dos revisores (contrato de API explícito, infraestrutura de teste com banco, distinção entre erro pré-stream e mid-stream, eval com perguntas negativas).
- Verificar contra a API real, antes da fase de embeddings, que um lote de N textos devolve N vetores distintos — o comportamento difere entre modelos de embedding e nenhum teste offline detecta a falha.
- Calibrar `SIMILARITY_THRESHOLD` com a distribuição de similaridade medida pelo `make eval`, e registrar o valor com a justificativa no `.env.example`.
- Adicionar `ygorbalves` como colaborador do repositório privado antes de responder à YAITEC.
