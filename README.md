# TalkDoc

Envie um PDF e converse com ele: as respostas são fundamentadas no documento e
trazem os trechos consultados com página e similaridade.

> Desafio técnico YAITEC Solutions — Desenvolvedor(a) AI / Full Stack.

## Setup

Pré-requisitos: Docker e Docker Compose.

```bash
cp .env.example .env      # preencha GEMINI_API_KEY
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000 (docs em `/docs`)

### Desenvolvimento

`docker compose up --build` serve o build estático pelo nginx — é o que se
entrega, e uma alteração no código só aparece depois de reconstruir a imagem.
Para iterar, use:

```bash
make dev
```

O código do host é montado nos containers: o frontend sobe no servidor do Vite
com HMR e o backend no uvicorn com `--reload`, nas mesmas portas. Os dois modos
disputam a 5173, então pare um antes de subir o outro.

## Exemplo de uso

1. Abra `http://localhost:5173`.
2. Envie um PDF com texto extraível.
3. Espere a leitura terminar; a tela abre o chat automaticamente.
4. Faça uma pergunta sobre uma informação presente no documento.

O TalkDoc responde com os trechos consultados e a respectiva página. Em seguida,
faça uma pergunta de continuação sobre a mesma informação: o histórico da
conversa é usado para transformar a continuação em uma pergunta autocontida
antes da busca.

Se a pergunta não estiver no PDF, o chat responde explicitamente que não
encontrou essa informação no documento, sem inventar uma resposta.

## Arquitetura

O projeto tem três serviços: React/Vite servido por nginx, FastAPI e PostgreSQL
com pgvector. O Docker Compose sobe os três; a chave do Gemini fica apenas no
arquivo `.env`, nunca no frontend.

No backend, as dependências fluem para dentro:

- `api/` recebe HTTP e SSE;
- `adapters/` integra Gemini, PostgreSQL e extração de PDF;
- `core/` concentra chunking, retrieval e montagem de prompts sem I/O.

O pipeline de RAG é próprio: o PDF é extraído página a página, quebrado em
chunks que nunca atravessam uma página, embedado em lote e salvo com vetor de
768 dimensões no pgvector. Para cada pergunta, o sistema combina busca vetorial
e lexical, aplica um limiar de fundamentação e envia os trechos recuperados ao
modelo. A resposta retorna as citações estruturadas que a interface exibe.

Conversas e mensagens são persistidas no PostgreSQL. Quando existe histórico,
perguntas de continuação são condensadas para uma consulta autocontida; se o
provedor não responder a tempo, o sistema usa um fallback determinístico e
mantém a conversa utilizável.

## Qualidade e segurança

- Upload tem limites de tamanho, páginas e texto extraído, com mensagens claras.
- A API usa um envelope de erro único e logs JSON sem conteúdo do PDF ou chaves.
- O projeto inclui lint, type-check estrito, contratos de arquitetura, testes e
  auditoria de dependências em `make check` e `make security`.
- O upload, o processamento, o streaming, as citações, a recusa fundamentada e
  a recuperação da conversa após recarregamento foram verificados no stack real.

## Ferramentas de IA usadas no desenvolvimento

O produto usa Google Gemini para embeddings e geração de respostas. Durante o
desenvolvimento, o OpenAI Codex foi usado para planejamento, implementação,
testes, revisão de diffs e documentação. As decisões de arquitetura e os
resultados de validação estão registrados em `.codeflow/`.

## Comandos de validação

```bash
make check      # lint + typecheck + test
make lint
make typecheck
make test
make security
```

`make check` executa lint, type-check, contratos de arquitetura e as suítes de
teste de backend e frontend. `make security` executa Bandit, pip-audit e npm
audit.

## Licença

MIT. Ver [LICENSE](LICENSE).
