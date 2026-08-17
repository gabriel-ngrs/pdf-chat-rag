---
spec: 01-ingestao-pdf
fase: B.3
slug_fase: upload-view
status: rework
tentativa: 2
reprovacoes: 1
sha_inicial: cb386f4
sha_final: 3be5eed
range: cb386f4..3be5eed
---

# FASE B.3 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/Yaitec-TalkDoc-trackB`, branch
> `feat/trackB-frontend`.

## ✅ Dependência `A.4` satisfeita na tentativa 2

Na tentativa 1 esta fase rodou com o Track A ainda em `A.1`, e o critério de
conclusão — "upload de ponta a ponta **através do `docker compose`**" — foi
cumprido contra um stub, o que gerou o BLOQUEANTE B-1 e a reprovação.

O Track A foi concluído e mergeado em `dev` (`9c5d8e8`). Nesta tentativa o gate
foi cumprido **contra o backend real**: `docker compose down -v && docker compose
up --build`, `.env` com `GEMINI_API_KEY` válida, e o `Exemplo-YAITEC.pdf`
percorrendo o caminho inteiro pelo nginx. As saídas estão na §5.

## 1. Resumo do que foi feito

A tela de envio existe: área de soltar que aceita clique, arrastar e teclado,
validação local contra os limites que o servidor informou, exibição de nome e
tamanho do arquivo escolhido, indicador indeterminado durante o envio e
persistência do `id` devolvido no `202`.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `frontend/src/hooks/useUpload.ts` | Estado do envio (`idle / sending / error`), `validateSelection()` e `formatFileSize()` |
| `frontend/src/components/UploadDropzone.tsx` | A tela: área de soltar, arquivo escolhido, botão de enviar |
| `frontend/src/hooks/useUpload.test.ts` | Testes da validação local e da formatação de tamanho |
| `frontend/src/components/UploadDropzone.test.tsx` | *(tentativa 2)* 10 testes de comportamento do componente e do hook de envio |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `frontend/src/App.tsx` | Monta o dropzone, guarda o `documentId` em `localStorage` e o restaura no boot |

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `uploadDocument()` e `ApiError` vêm do `api.ts` da `B.2` —
nenhuma chamada `fetch` nova foi escrita. As mensagens de recusa vêm do
`errors.ts` da `B.2` via `notify.error(code)`; nenhuma frase de erro foi
duplicada no componente. `Card`, `Button` e os tokens vêm da `B.1`; o componente
não define nenhuma cor própria.

**Decisões de design:**

1. **O `<input type="file">` vive dentro do `<label>`.** Primeira tentativa
   deixou o input como irmão do label; `:has(input:focus-visible)` só casa
   descendentes, e o resultado media era a borda neutra — ou seja, **quem
   chegasse pela tecla Tab não veria foco nenhum**, porque o único elemento
   focável é visualmente oculto. Corrigido movendo o input para dentro. Medido
   depois: `border-color` do label vira `oklch(0.58 0.16 62)` (o token `--ring`).
2. **Sem botão "trocar arquivo" separado.** A própria área de soltar continua
   sendo o alvo depois da escolha ("Clique ou arraste outro arquivo para
   trocar"), o que evita dois pontos de foco fazendo a mesma coisa.
3. **`validateSelection` é função pura, fora do componente.** É o que torna
   AC-20 testável sem DOM e sem navegador.
4. **Sem limites conhecidos, sem bloqueio por tamanho.** Em config degradada a
   checagem de tamanho não roda — testado. Bloquear com um número inventado
   seria pior que deixar o servidor recusar.
5. **Nome do arquivo com `break-all`.** Nome longo de PDF quebra o layout a
   375 px se não quebrar linha.

Nenhum desvio da spec além da dependência `A.4` declarada no topo.

## 5. Comandos rodados + saídas reais

```text
# testes (frontend)
$ npm --prefix frontend run test
 Test Files  3 passed (3)
      Tests  16 passed (16)

# type-check e lint
$ cd frontend && npx tsc --noEmit    # exit 0
$ cd frontend && npm run lint        # exit 0

# TENTATIVA 2 — compose real, com a A.4 na árvore
$ docker compose down -v && docker compose up --build -d
Container yaitec-talkdoc-trackb-db-1        Healthy
Container yaitec-talkdoc-trackb-backend-1   Started
Container yaitec-talkdoc-trackb-frontend-1  Started

$ curl -s -i http://localhost:5173/api/health | head -8
HTTP/1.1 200 OK
Server: nginx/1.27.5
Content-Type: application/json
x-request-id: 15c4aca5-8483-419e-bb31-d671e2075516

$ curl -s http://localhost:5173/api/config
{"max_upload_mb":25,"max_pdf_pages":20,"max_extracted_chars":60000}

# AC-2 — 28 MB através do nginx: JSON do envelope, não HTML do nginx
$ curl -s -o /dev/null -w "status=%{http_code} tipo=%{content_type}\n" \
    -F "file=@big.pdf" http://localhost:5173/api/documents
status=413 tipo=application/json
$ curl -s -F "file=@big.pdf" http://localhost:5173/api/documents
{"code":"arquivo_grande","message":"O arquivo excede o limite de 25 MB."}

# AC-3 — .txt renomeado para .pdf, recusado pelo servidor
$ curl -s -F "file=@planilha.txt;filename=disfarcado.pdf" http://localhost:5173/api/documents
{"code":"arquivo_invalido","message":"O arquivo enviado não é um PDF. Envie um documento com extensão .pdf válida."}

# 404 — o código que o errors.ts mapeia
$ curl -s http://localhost:5173/api/documents/00000000-0000-0000-0000-000000000000
{"code":"nao_encontrado","message":"Documento não encontrado."}

# gate da fase, contra o backend real
$ python3 audit_upload.py http://localhost:5173
{
  "ac20_aviso": [{
    "title": "Arquivo grande demais",
    "description": "O arquivo tem 31,0 MB e o limite é 25 MB. Envie um arquivo menor ou divida o documento em partes.",
    "type": "error"
  }],
  "ac20_nenhum_post": true,
  "ac20_botao_enviar_desabilitado": true,
  "nao_pdf_aviso": [{
    "title": "Arquivo não é um PDF válido",
    "description": "Só é possível enviar arquivos PDF. Confira se o arquivo abre no seu leitor e envie de novo.",
    "type": "error"
  }],
  "nao_pdf_nenhum_post": true,
  "ac23_foco_no_input": "file",
  "ac23_area_destacada": "oklch(0.58 0.16 62)",
  "ac21_nome_visivel": true,
  "ac21_tamanho_visivel": true,
  "gate_post_enviado": ["POST http://localhost:5173/api/documents"],
  "gate_id_persistido": "bd1ee92a-6abc-4807-bab5-39315c2e4aa4",
  "gate_aviso_sucesso": [{"title": "Documento recebido. Começando a leitura.", "type": "success"}]
}
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-20** — arquivo de 31 MB com limite de 25 MB é recusado **antes** da
  requisição: `ac20_nenhum_post: true` (nenhum `POST` no log de rede da página)
  e o aviso traz título, o tamanho real medido e a ação sugerida, em pt-BR.
- [x] **AC-21** — PDF válido mostra nome (`Exemplo-YAITEC.pdf`) e tamanho
  (`254 KB`, em fonte mono para comparar com o limite); durante o envio aparece
  "Enviando o arquivo…" com `role="status"` e ícone girando.
- [x] **AC-23 (parte de teclado)** — o terceiro `Tab` da página chega ao input
  de arquivo e a área de soltar destaca a borda com o token `--ring`; o botão
  "Enviar documento" é o quarto ponto de foco.
- [x] **AC-1** — `POST /api/documents` pelo nginx devolve `202` com
  `{"id": "0285208b-…", "status": "pending"}` e o processamento segue em
  background (§5 do relatório da `B.4`).
- [x] **AC-2** — 28 MB através do nginx: `413` com
  `Content-Type: application/json` e corpo `{"code":"arquivo_grande", …}`.
  **Não é HTML do nginx** — que era exatamente o risco.
- [x] **AC-3** — `.txt` renomeado para `.pdf` recusado pelo **servidor** com
  `422` e `code: "arquivo_invalido"`.
- [x] **Recusa de formato no cliente** — arquivo cujo nome **e** tipo MIME não
  são de PDF é bloqueado antes da requisição. Um `.txt` com o nome trocado para
  `.pdf` **passa** pelo cliente por construção (a checagem é extensão-ou-MIME) e
  é recusado pelo servidor: é o servidor quem lê a assinatura `%PDF`, e AC-3 é
  dele. Ver a correção D-1 na §8.
- [x] **Critério de conclusão da fase** — upload de ponta a ponta **através do
  `docker compose`** com o backend da `A.4`. Cumprido na tentativa 2.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (10 testes de componente + 6 de lógica pura)
- [x] `make check` inteiro retorna zero (lint, typecheck, arch, 119 testes de
  backend, 40 de frontend); `make security` zero
- [x] Escopo travado respeitado: validação do cliente não substitui a do
  servidor, nenhum outro formato aceito, **nenhuma barra de progresso de upload
  prometida**, nenhuma cor fora dos tokens
- [x] Nenhum segredo/PII em log, DTO ou exceção
- [x] Commits em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

Avaliação da tentativa 1: **REPROVADO**, score 8,8. Um BLOQUEANTE, um
IMPORTANTE, uma divergência e quatro sugestões.

### B-1 — gate não cumprido contra o backend real → **corrigido**

O Track A foi concluído e mergeado em `dev`. `docker compose up --build` com a
`A.4` real, e o ciclo rodou pelo nginx do projeto. Além do gate, os três
caminhos que só o servidor pode provar foram exercitados e batem com o
`errors.ts`: `413 arquivo_grande` (em JSON, não HTML), `422 arquivo_invalido` e
`404 nao_encontrado`. Saídas na §5.

### I-1 — nenhum teste de componente nem de hook → **corrigido**

`src/components/UploadDropzone.test.tsx`, 10 testes com
`@testing-library/react` + `jsdom`, cobrindo o que o avaliador listou: seleção
por `input` **e** por arrastar, limpeza do campo após recusa, `sending`
bloqueando campo e botão, o `notify.error` com a mensagem específica, e
`onAccepted` disparando só quando o servidor aceita. Mais um caso que o
avaliador não pediu e vale ter: sem limites conhecidos, nada é bloqueado por
tamanho.

### D-1 — divergência entre relatório e código → **corrigida**

A tentativa 1 afirmava "`.txt` renomeado é bloqueado no cliente". Não é o que
`useUpload.ts:39` faz: a checagem é `type === 'application/pdf' ||
name.endsWith('.pdf')`, então um `.txt` renomeado **passa** pelo cliente. O
avaliador testou e está certo. O **código está correto** — quem lê a assinatura
`%PDF` é o servidor, e AC-3 é dele por construção. A frase da §6 foi reescrita
para dizer o que o código faz, e o teste novo separa os dois casos.

### Sugestões acatadas

- **S-1, `onDragLeave` piscava.** `dragleave` borbulha, então entrar num filho
  apagava o destaque por um frame. O handler agora confere
  `currentTarget.contains(relatedTarget)`.
- **S-2 e S-4** — o avaliador registrou concordância com o código atual
  (tratamento de `limits` degradado no `drop`; ausência de botão "trocar
  arquivo" separado). Sem mudança.

## 9. Itens em aberto / dúvidas para o avaliador

1. **O painel após o `202` é da `B.4`** — nesta fase ele só existe como ponte.
2. **O `413` do servidor continua sem exercício pela interface**, porque o
   cliente bloqueia antes e só chegaria lá quem estivesse com a config
   degradada. O caminho de código existe e está testado
   (`UploadDropzone.test.tsx`, caso de falha do servidor com `limite_de_uso`); o
   `413` em si foi provado por `curl` através do nginx, na §5.
3. **A verificação de DOM por Playwright continua fora do repositório.** Agora
   ela é redundante com os testes versionados — mantive o registro na §5 como
   evidência de que o gate rodou no container, não como suíte.
