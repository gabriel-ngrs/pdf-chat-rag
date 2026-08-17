---
spec: 01-ingestao-pdf
fase: B.3
slug_fase: upload-view
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: cb386f4
sha_final: 2e43df0
range: cb386f4..2e43df0
---

# FASE B.3 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/Yaitec-TalkDoc-trackB`, branch
> `feat/trackB-frontend`.

## ⚠️ Dependência `A.4` não satisfeita — leia antes de avaliar

A fase declara **"Depende de: `B.2`, `A.4`"**. No momento da execução, o Track A
está em `A.1` (executada, aguardando avaliação) — `A.2`, `A.3` e `A.4` não
existem em nenhuma branch. O protocolo do `/execute-spec-phase` mandaria
**parar** aqui (Passo 3, linha 5 da tabela de seleção).

Segui por instrução explícita do usuário ("execute todas as fases da track B, em
sequência"). O que isso significa em concreto:

- **O código não depende da `A.4`.** O contrato de §4.5 é fonte única e foi
  escrito antes das fases; a própria spec manda escrever `types.ts` a partir
  dela, "não de `schemas.py`, que pode ainda não existir quando esta fase roda".
- **O gate depende.** "Upload de ponta a ponta **através do `docker compose`**"
  não pôde ser cumprido contra o backend real. Foi cumprido contra o **nginx do
  container real** (mesma imagem, mesmo `nginx.conf`, mesmo `client_max_body_size`,
  mesmo prefixo `/api`) apontando para um **backend-stub fiel à §4.5**, rodando
  no host via `--add-host backend:host-gateway`. O stub vive no scratchpad da
  sessão e **não** foi commitado.
- **O que continua pendente:** revalidar `AC-1`, `AC-2` e `AC-3` contra o
  backend da `A.4` na integração dos dois tracks. Em particular o `413` do
  nginx e o `422` de assinatura, que são caminhos do servidor.

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

# container real (imagem do Dockerfile) + backend-stub fiel à §4.5
$ docker run -d --name talkdoc-b3 --add-host backend:host-gateway -p 5173:80 talkdoc-frontend:b3
$ curl -s http://localhost:5173/api/config
{"max_upload_mb": 25, "max_pdf_pages": 20, "max_extracted_chars": 60000}

# gate da fase
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
  "gate_id_persistido": "69da5caf-890a-42cc-b770-9a44781300b8",
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
- [x] **Recusa de formato** — `.txt` renomeado é bloqueado no cliente, sem
  requisição. (O `422` do servidor, `AC-3`, continua sendo responsabilidade da
  `A.4` e será revalidado na integração.)
- [~] **Critério de conclusão da fase** — "upload de ponta a ponta através do
  `docker compose`": cumprido através do **nginx do container real** contra o
  backend-stub; **pendente** contra o backend da `A.4`. Ver o aviso no topo.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (16/16)
- [x] `tsc --noEmit` e `eslint` zero; gates de backend `[—]` justificados
- [x] Escopo travado respeitado: validação do cliente não substitui a do
  servidor, nenhum outro formato aceito, **nenhuma barra de progresso de upload
  prometida**, nenhuma cor fora dos tokens
- [x] Nenhum segredo/PII em log, DTO ou exceção
- [x] Commits em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **O gate contra o backend real da `A.4` não foi cumprido** — é o item mais
   importante deste relatório. Ver o aviso no topo.
2. **O caminho do `413` do servidor não foi exercitado na interface.** Como o
   cliente bloqueia antes, só chega ao servidor quem estiver com a config
   degradada. O tratamento existe (`ApiError` → `notify.error('arquivo_grande')`),
   mas quem prova que o nginx devolve JSON e não HTML é a `A.1`/`A.4`.
3. **Não há teste de componente**, só de lógica pura (`validateSelection`,
   `formatFileSize`). O comportamento de DOM foi verificado por Playwright
   contra o container, com a saída colada acima, mas esse script não está
   versionado. Se o avaliador quiser isso no repositório, o caminho é
   `@testing-library/react` + `jsdom` numa fase própria.
4. **O painel "Documento recebido" que aparece após o `202` é provisório** — a
   `B.4` o substitui pelo acompanhamento de verdade.
