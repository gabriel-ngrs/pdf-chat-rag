# TalkDoc

Envie PDFs e converse com eles: respostas fundamentadas no documento via RAG, com citação de trecho e página.

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

<!-- TODO: preencher após a primeira feature — upload de um PDF e uma pergunta de exemplo com a resposta citando a página. -->

## Arquitetura

<!-- TODO: preencher — decisões de arquitetura e justificativas (chunking, embeddings, retrieval, memória de conversa). -->

## Ferramentas de IA usadas no desenvolvimento

<!-- TODO: preencher — quais assistentes de IA foram usados e como. -->

## Comandos de validação

```bash
make check      # lint + typecheck + test
make lint
make typecheck
make test
make security
```

## Licença

MIT. Ver [LICENSE](LICENSE).
