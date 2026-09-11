---
spec: 01-ingestao-pdf
fase: B.3
slug_fase: upload-view
tentativa: 2
veredito: APROVADO
score: 9.8
threshold: 8.5
range_avaliado: cb386f4..3be5eed
---

# FASE B.3 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.8 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. Os dois achados da tentativa 1 estão
fechados, e **não aceitei a palavra do relatório em nenhum deles**: subi o
`docker compose` a partir de volume vazio, com o backend da `A.4`, e exercitei
eu mesmo os caminhos de servidor que a tentativa 1 não pôde exercitar.

O que mais importa: **AC-2 passou**. Um arquivo de 28 MB através do nginx volta
`413` com `Content-Type: application/json` e `{"code":"arquivo_grande"}` — não
HTML do nginx. Esse era o risco concreto por trás do bloqueante, o que o
`client_max_body_size 30m` de §4.1 existe para evitar, e o único jeito de saber
era com o proxy e o backend reais no caminho.

## 2. Nota sobre a elegibilidade (§2.11.4) — por que isto não reprova de novo

A fase declara `Depende de: B.2, A.4`. Na tentativa 1, `A.4` **não existia** e o
gate era fisicamente impossível — daí o BLOQUEANTE. Agora `A.4` está na árvore,
mas sua avaliação é `RESSALVAS` na tentativa 1, o que pela §2.11.3 a mantém
formalmente **reprovada**; pela letra da §2.11.4 a `B.3` ainda não seria elegível.

Não repito a reprovação, e a razão é substantiva, não indulgente. Li os dois
achados IMPORTANTES da `A.4` e nenhum toca o contrato que esta fase consome:

- **A.4 I-1** — documento `failed` deduplicado para sempre. Muda o comportamento
  de reenvio, não a forma da resposta. Depois de corrigido, o `POST` devolve
  `202 {id, status}` do mesmo jeito; o cliente só melhora.
- **A.4 I-2** — docstrings faltando em `adapters/repository.py`. Sem superfície
  externa.

E não me apoiei só nessa leitura: **li o payload cru do backend real** (§6 da
avaliação da `B.4`) e ele traz exatamente os sete campos da §4.5, nem um a mais
nem um a menos. O risco que o bloqueante nomeava está medido, não presumido.

Reprovar de novo aqui empurraria a fase para `reprovacoes: 2` — a um passo do
teto de escalação da §2.11.4 — por um motivo que nenhum rework de `B.3` pode
resolver. Isso é o teto de tentativas fazendo o oposto do que existe para fazer.
Registro a pendência formal na §7 e no fechamento da FEAT-0001, onde ela é
acionável.

## 3. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | **Contra o backend real, medido por mim:** AC-1 `202 {"id":"657457…","status":"pending"}` pelo nginx; AC-2 `413` `application/json` `{"code":"arquivo_grande"}`; AC-3 `422 arquivo_invalido` para `.txt` renomeado; `404 nao_encontrado`. **No navegador:** AC-20 (31 MB recusado sem nenhum `POST`, aviso com o tamanho real), AC-21 (`documento-de-exemplo.pdf \| 254 KB`), AC-23 (input é o 3º ponto de foco, `:focus-visible`, borda do label em `oklch(0.58 0.16 62)`). Escopo travado: `grep` de `XMLHttpRequest\|onUploadProgress` = 0, nenhuma cor fora dos tokens, nenhum outro formato aceito |
| 2 | Arquitetura e direção de dependências | 3 | 5 | Lógica pura em `useUpload.ts` fora do componente; rede só via `api.ts` da `B.2` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `useUpload.ts:31-37` continua declarando que a validação local não substitui a do servidor — e agora isso está **provado**: o `.txt` renomeado passa pelo cliente e é o servidor que devolve `422`. `grep` de segredo = 0; `make security` = 0 |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `uploadDocument`, `ApiError` e as frases do `errors.ts` reusados; nenhuma mensagem duplicada no componente |
| 5 | Padrões de domínio/aplicação | 2 | 5 | União discriminada no estado do envio; `SelectionProblem` carrega só o que é específico e delega o resto ao mapa |
| 6 | Local e nomes dos arquivos | 2 | 5 | `UploadDropzone.test.tsx` é o único arquivo novo do rework nesta fase, no lugar certo |
| 7 | Qualidade de código | 2 | 4 | O conserto do `onDragLeave` (`UploadDropzone.tsx:86-92`) é o certo: `currentTarget.contains(relatedTarget)`, com o "por quê" no comentário. Desconto pelos identificadores em pt-BR do arquivo de teste (`campoDeArquivo`, `montar`, `titulo`, `opcoes`, `texto`) — ver §6 |
| 8 | Testes e cobertura | 2 | 5 | 10 testes de componente + 6 de lógica pura, **todos dentro do `make check`**. Cobrem o que a avaliação anterior listou e mais: seleção por `input` e por `drop`, limpeza do campo após recusa, `sending` bloqueando campo e botão, aviso por código, `onAccepted` só quando o servidor aceita, e config degradada não bloqueando |
| 9 | Migration safety (se aplicável) | 2 | — | Não se aplica |

Média ponderada (dimensões 1–8, peso total 20): 98/20 = 4,9 → **9,8/10**.

## 4. Achados BLOQUEANTES

Nenhum.

**B-1 da tentativa 1 (gate não cumprido contra o backend real) — FECHADO.**
Subi o compose eu mesmo, de volume vazio, a partir do worktree que está no mesmo
commit que `dev` (`7b36f53`; confirmei que as árvores de código são idênticas). A
única diferença que introduzi foi deixar de publicar a porta 5432 do Postgres,
porque outro compose já a ocupava — o próprio `docker-compose.yml` declara que
essa publicação existe para testes de integração e "não é necessária para a
aplicação em si". Saídas na §6.

## 5. Achados IMPORTANTES

Nenhum.

**I-1 da tentativa 1 (sem teste de componente nem de hook) — FECHADO.**
`UploadDropzone.test.tsx`, 10 testes com `@testing-library/react` + `jsdom`,
verdes na minha execução e dentro do gate. Confirmei os três casos que eu tinha
desenhado (limite antes da requisição, nome e tamanho na tela, `sending`
bloqueando) e mais sete.

**D-1 da tentativa 1 (divergência de redação) — CORRIGIDA, e agora provada.** A
§6 do relatório descreve o que `useUpload.ts:39` faz de fato — a checagem é
extensão-**ou**-MIME, um `.txt` renomeado passa pelo cliente, e a assinatura
`%PDF` é do servidor. O teste `recusa arquivo que não é PDF`
(`UploadDropzone.test.tsx:111-122`) separa os dois casos, com o `applyAccept:
false` comentado pela razão certa: `accept` é filtro do seletor, não garantia.

Fui além e medi a divisão de responsabilidade inteira no navegador, contra o
backend real (§7): ao escolher `disfarcado.pdf` (nome `.pdf`, conteúdo texto) o
cliente **aceita** — nenhum aviso, nenhum `POST`, o arquivo aparece na área; ao
enviar, sai o `POST`, o servidor devolve `422` e a tela mostra "Arquivo não é um
PDF válido". A mensagem exibida é a do mapa, **sem** o override que a validação
local usaria — ou seja, é comprovadamente o servidor recusando. É exatamente o
que o escopo travado da fase manda ("validação no cliente não substitui a do
servidor") e o que AC-3 exige.

## 6. Sugestões

1. **Identificadores em pt-BR em `UploadDropzone.test.tsx`** (`campoDeArquivo`,
   `montar`, `pdf`, `titulo`, `opcoes`, `texto`, `arquivo`, `concluir`). A spec
   fixa "identificadores em inglês" em §1.1 item 8 e na DoD global. Os **nomes
   dos casos** em pt-BR estão certos e devem ficar — é documentação de
   comportamento para quem lê o projeto. Não bloqueio: a spec põe esse item em
   "Itens globais transversais" da §9, não no gate por fase, e parte do padrão já
   existia na tentativa 1 sem eu apontar. Fica para o fechamento da FEAT-0001.
2. **`UploadDropzone.test.tsx:84` usa `campoDeArquivo().closest('div')!`** para
   achar a zona de `drop`. Amarra o teste à estrutura de `div`s do componente:
   mover o handler um nível quebra o teste sem quebrar o comportamento. Um
   `data-testid` na zona, ou disparar o `drop` no `label`, sobrevive à
   refatoração.
3. **O caminho `413` continua sem exercício pela interface** — o executor já
   registra isso na §9.2. Está correto do jeito que está: o cliente bloqueia
   antes, e quem chega ao servidor só chega com config degradada. Provei o `413`
   por `curl` através do nginx e o tratamento por teste (`limite_de_uso`), que
   juntos cobrem o par. Nenhuma ação.

## 7. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 3be5eed HEAD
3be5eed ancestor OK

# compose real, do worktree no mesmo commit que dev, volume novo
$ docker compose -f docker-compose.yml -f <override que não publica a 5432> up --build -d
 Container talkdoc-trackb-db-1        Healthy
 Container talkdoc-trackb-backend-1   Started
 Container talkdoc-trackb-frontend-1  Started

$ curl -s -i http://localhost:5173/api/health | head -5
HTTP/1.1 200 OK
Server: nginx/1.27.5
Content-Type: application/json

$ curl -s http://localhost:5173/api/config
{"max_upload_mb":25,"max_pdf_pages":20,"max_extracted_chars":60000}

# AC-2 — 28 MB através do nginx
$ curl -s -o r.txt -w "status=%{http_code} tipo=%{content_type}\n" -F "file=@big.pdf" \
    http://localhost:5173/api/documents
status=413 tipo=application/json
$ cat r.txt
{"code":"arquivo_grande","message":"O arquivo excede o limite de 25 MB."}

# AC-3 — .txt renomeado para .pdf
$ curl -s -w "\nstatus=%{http_code} tipo=%{content_type}\n" -F "file=@disfarcado.pdf" \
    http://localhost:5173/api/documents
{"code":"arquivo_invalido","message":"O arquivo enviado não é um PDF. Envie um documento com extensão .pdf válida."}
status=422 tipo=application/json

# 404
$ curl -s -w "\nstatus=%{http_code}\n" http://localhost:5173/api/documents/00000000-0000-0000-0000-000000000000
{"code":"nao_encontrado","message":"Documento não encontrado."}
status=404

# AC-1 e gate da fase — ciclo pelo navegador, contra o compose real
$ python3 gate.py
 "antes_do_envio": "documento-de-exemplo.pdf | 254 KB | Clique ou arraste outro arquivo para trocar."
 "posts": ["http://localhost:5173/api/documents"]
 "id_em_storage": "65745776-fa91-42e3-ad8b-2d3c607c51f8"
 "apos_reset": {"storage": null, "voltou_ao_envio": true}

# AC-20 no navegador — 26 MB com limite de 25 MB
$ python3 ac20b.py
 "ac20": {
   "toasts": ["Arquivo grande demais | O arquivo tem 26,0 MB e o limite é 25 MB.
               Envie um arquivo menor ou divida o documento em partes."],
   "posts": [],                      <- nenhuma requisição saiu
   "botao_desabilitado": [true]
 }

# D-1 corrigida, provada de ponta a ponta: cliente deixa passar, servidor recusa
 "txt_apos_escolher": {"toasts": [], "posts": [],
                       "label": "disfarcado.pdf | 9 B | Clique ou arraste outro arquivo para trocar."}
 "txt_apos_enviar":   {"toasts": ["Arquivo não é um PDF válido | O conteúdo enviado não
                                   abre como PDF. Confira se o arquivo abre no seu leitor…"],
                       "posts": ["http://localhost:5173/api/documents"],
                       "respostas": [["POST", 422, "http://localhost:5173/api/documents"]]}
 A mensagem exibida é a do mapa (`errors.ts`), sem o override do cliente — prova de
 que quem recusou foi o `422` do servidor, e não a validação local.

# AC-21 e AC-23 no navegador
 "antes_do_envio": "documento-de-exemplo.pdf | 254 KB | Clique ou arraste outro arquivo para trocar."
 3o Tab -> {"tag":"input","type":"file","focusVisible":true,
            "caixaFoco":{"borderColor":"oklch(0.58 0.16 62)","boxShadow":"… 0px 0px 0px 3px"}}

# contraste e responsividade, re-medidos após o rework (nenhuma regressão)
 desktop-light 18 pares, 0 reprovados, pior 7.17, overflow_x 0
 desktop-dark  18 pares, 0 reprovados, pior 7.15, overflow_x 0
 mobile-light  18 pares, 0 reprovados, pior 7.17, overflow_x 0
 mobile-dark   18 pares, 0 reprovados, pior 7.15, overflow_x 0

$ make check      # 119 backend (cobertura core 98.98%) + 40 frontend
MAKE_CHECK_EXIT=0
$ make security
MAKE_SECURITY_EXIT=0

$ grep -rnE "XMLHttpRequest|onUploadProgress|upload\.onprogress" frontend/src
(vazio)
$ grep -rniE "GEMINI_API_KEY|DATABASE_URL|/home/gabriel|AIza" frontend/src
(vazio)

$ git status --short
(vazio — árvore limpa ao final)
```

## 8. Itens da fase / DoD não atendidos

Nenhum item da fase. O critério de conclusão — "upload de ponta a ponta através
do `docker compose`" — está cumprido e verificado de forma independente.

**Pendências da FEAT-0001, não desta fase:**

- `A.4` estava formalmente **reprovada** (`RESSALVAS`, tentativa 1) quando esta
  avaliação começou — ver §2. Durante a redação, o rework do Track A foi mergeado
  em `dev` (`7c2d6a4`) e uma sessão paralela passou a gravar as avaliações de
  tentativa 2. Conferi o que o merge fez com o que medi: `frontend/` e `Makefile`
  intactos, e **`backend/app/api/schemas.py` intacto** — ou seja, o contrato da
  §4.5 que eu li do backend real continua valendo, e o re-check que eu tinha
  ressalvado deixou de ser necessário. `make check` re-rodado no HEAD: exit 0. O
  fechamento da spec segue dependendo de `APROVADO` em todas as fases do Track A.
- "Identificadores em inglês" (DoD global) — §6.1.

## 9. Divergências entre o relatório e o código real

Nenhuma. Confrontei cada saída da §5 do relatório com medição própria e todas
batem: `413` em JSON, `422 arquivo_invalido`, `404 nao_encontrado`, `202` com
`{id, status}`, `ac20_nenhum_post`, nome e tamanho na tela, `--ring` na borda do
label sob foco de teclado. Os valores de id diferem, como esperado — são
execuções diferentes.

A correção da D-1 está honesta: o relatório agora diz que o `.txt` renomeado
**passa** pelo cliente e é recusado pelo servidor, que é exatamente o que o
código faz e o que a spec manda.
