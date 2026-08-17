---
spec: 01-ingestao-pdf
fase: B.4
slug_fase: processing-status
status: executado
tentativa: 1
reprovacoes: 0
sha_inicial: f00210e
sha_final: e93a748
range: f00210e..e93a748
---

# FASE B.4 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/Yaitec-TalkDoc-trackB`, branch
> `feat/trackB-frontend`.

## ⚠️ Mesma ressalva da `B.3`

Esta fase depende de `B.3`, que por sua vez declara depender de `A.4` — não
executada. A verificação foi feita contra o **container real** (imagem do
`Dockerfile`, `nginx.conf` do projeto) apontando para um **backend-stub fiel à
§4.5**, que reproduz a máquina de estados de FR-9, a janela em que
`chunks_total` ainda é `null` e o caminho de `failed` com `error_message`.
Revalidar contra a `A.4` na integração.

## 1. Resumo do que foi feito

O ciclo `enviando → na fila → lendo → pronto` (ou `falhou`) é visível sem
recarregar, com barra indeterminada enquanto o total de trechos é desconhecido e
determinada depois. O polling para em estado terminal, limpa o timer ao
desmontar e não derruba a tela quando a rede falha. Recarregar a página retoma o
acompanhamento. Falha exibe a mensagem que o backend mandou.

## 2. Arquivos CRIADOS

| Arquivo | Propósito |
|---------|-----------|
| `frontend/src/hooks/useDocumentStatus.ts` | Polling com parada em estado terminal, limpeza de timer e `progressPercent()` |
| `frontend/src/components/ProcessingStatus.tsx` | Os quatro estados, a barra e a saída para enviar outro documento |
| `frontend/src/hooks/useDocumentStatus.test.ts` | Testes de `progressPercent` (o que ela recusa a inventar) |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `frontend/src/App.tsx` | Troca o painel provisório da `B.3` pelo acompanhamento e acrescenta `handleReset` |

**Declarado na spec mas não alterado:** `frontend/src/components/UploadDropzone.tsx`.
Não foi preciso — o `App` é quem alterna entre envio e acompanhamento, então
"passar o controle" não exigiu mudança no dropzone. Menos diff, não mais.

## 4. Confirmação do REUSO e decisões de design

**Reuso confirmado.** `fetchDocument()` e `ApiError` vêm do `api.ts` da `B.2`;
`describeError('nao_encontrado')` vem do `errors.ts` da `B.2` — a mensagem de
documento inexistente não foi reescrita. `Card`, `Progress`, `Skeleton`, `Badge`
e `Button` vêm do design system da `B.1`; nenhuma cor nova foi definida.

**Decisões de design:**

1. **Intervalo de 1,5 s.** A spec exige "não mais agressivo que 1 s"; o backend
   atualiza o progresso no máximo a cada 15 s (NFR-1), então perguntar mais
   rápido não revela nada. Medido: menor intervalo real observado, 1,51 s.
2. **Cadeia de `setTimeout`, não `setInterval`.** O próximo ciclo só é agendado
   depois que o anterior respondeu — com `setInterval`, uma resposta lenta
   empilharia requisições.
3. **Falha de rede mantém o último estado; `404` não.** `nao_encontrado` é
   terminal (o id salvo não existe mais no servidor) e leva à tela de recuperação
   com a ação de enviar outro documento. Qualquer outra falha é tratada como
   transitória e o ciclo seguinte tenta de novo.
4. **Clamp monotônico na apresentação.** `progressPercent` é pura e derivada só
   do que o backend informou; o `useMonotonicPercent` do componente guarda o
   maior valor já mostrado para que uma resposta fora de ordem não faça a barra
   voltar. Não é inventar progresso — é não desfazer na tela o que o usuário já
   viu.
5. **`aria-valuenow` e `aria-valuetext` explícitos na barra.** Medido antes: o
   primitivo desenhava a barra com `role="progressbar"` e `aria-valuemax`, mas
   **sem** `aria-valuenow` — uma barra que não diz nada a leitor de tela.
   Corrigido; medido depois: `valuenow: "33"`, depois `"67"`.
6. **`role="status"` na linha de estado.** Região polida, como a fase pede.
   Anuncia "Na fila" → "Lendo o documento" → "Pronto" conforme muda.

Nenhum desvio da spec além da dependência declarada no topo.

## 5. Comandos rodados + saídas reais

```text
# testes (frontend)
$ npm --prefix frontend run test
 Test Files  4 passed (4)
      Tests  20 passed (20)

# type-check e lint
$ cd frontend && npx tsc --noEmit    # exit 0
$ cd frontend && npm run lint        # exit 0

# gate da fase, contra o container real + backend-stub da §4.5
$ python3 audit_processing.py http://localhost:5173
{
  "transicoes": [
    {"titulo": "Enviando o arquivo…", "valorBarra": null,  "barraIndeterminada": false},
    {"titulo": "Na fila",             "valorBarra": null,  "barraIndeterminada": true},
    {"titulo": "Lendo o documento",   "valorBarra": null,  "barraIndeterminada": true},
    {"titulo": "Lendo o documento",   "valorBarra": "33",  "barraIndeterminada": false},
    {"titulo": "Lendo o documento",   "valorBarra": "67",  "barraIndeterminada": false},
    {"titulo": "Pronto",              "valorBarra": null,  "barraIndeterminada": false}
  ],
  "chegou_em_pronto": true,
  "progresso_monotonico": true,
  "valores_da_barra": [33, 67],
  "teve_janela_indeterminada": true,
  "menor_intervalo_de_polling_s": 1.51,
  "polling_parou_em_pronto": true,
  "apos_f5": "Pronto",
  "aria": {"roleStatusPresente": true, "textoAnunciado": "Pronto"},
  "falha": {"titulo": "Não deu para processar",
            "texto": "… | Não deu para processar | Não foi possível extrair texto deste PDF; OCR não é suportado."},
  "reset_volta_ao_envio": true,
  "reset_limpou_storage": null
}

# semântica da barra durante o processamento
$ python3 probe_progress.py
{"titulo": "Lendo o documento", "role": "progressbar", "valuenow": "33",
 "label": "Progresso da leitura do documento", "legenda": "4 de 12 trechos · 33%"}
{"titulo": "Lendo o documento", "role": "progressbar", "valuenow": "67",
 "label": "Progresso da leitura do documento", "legenda": "8 de 12 trechos · 67%"}
```

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-22** — transição `enviando → na fila → lendo → pronto` observada numa
  única sessão de página, sem `reload` entre as amostras.
- [x] **AC-12** — `valores_da_barra: [33, 67]` em ordem crescente,
  `progresso_monotonico: true`; a legenda mostra "4 de 12 trechos", derivada de
  `chunks_processed`/`chunks_total`.
- [x] **AC-5 (lado da UI)** — documento `failed` exibe a `error_message` do
  backend palavra por palavra ("Não foi possível extrair texto deste PDF; OCR
  não é suportado."), não uma frase genérica, com a ação de enviar outro arquivo.
- [x] **Recarregar retoma o acompanhamento** — `apos_f5: "Pronto"`, lendo o id
  de `localStorage`.
- [x] **AC-23 (`aria-live`)** — `role="status"` presente e anunciando o estado
  corrente; barra com `role="progressbar"`, `aria-label`, `aria-valuenow` e
  `aria-valuetext`.
- [x] **Não inventa progresso** — houve janela indeterminada real
  (`teve_janela_indeterminada: true`) enquanto `chunks_total` era `null`, e os
  testes provam que `progressPercent` devolve `null` nesse caso.
- [x] **Sem timer órfão** — `polling_parou_em_pronto: true` (nenhuma requisição
  nova em 4 s após `ready`); o `useEffect` limpa o timeout no cleanup.
- [~] **Critério de conclusão da fase** — "ciclo observável no compose": cumprido
  no container real contra o stub; **pendente** contra a `A.4`.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (20/20 no total do frontend)
- [x] `tsc --noEmit` e `eslint` zero; gates de backend `[—]` justificados
- [x] Escopo travado respeitado: polling de 1,5 s (nunca abaixo de 1 s), timer
  limpo no cleanup, nenhum progresso inventado, nenhuma stack trace ou corpo
  bruto exibido
- [x] Nenhum segredo/PII em log, DTO ou exceção
- [x] Commits em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

Não se aplica — primeira execução.

## 9. Itens em aberto / dúvidas para o avaliador

1. **Revalidação contra a `A.4`** — o item que mais importa. Em especial: os
   nomes de campo (`chunks_processed`, `chunks_total`, `page_count`,
   `error_message`) e o fato de `chunks_total` chegar `null` antes do chunking.
   Se o backend divergir, quem está errado é o backend (a §4.5 é fonte única),
   mas alguém precisa conferir.
2. **1,5 s de polling é escolha minha** dentro do piso de 1 s da spec. Se o
   avaliador quiser um número diferente, é uma constante.
3. **`ready` não leva a lugar nenhum ainda** — o sinal é o selo "Pronto para
   conversar". A `FEAT-0002 B.1` é quem transforma isso em entrada de conversa.
4. **Não há teste de componente** para os quatro estados; só a lógica pura de
   `progressPercent` está versionada. O comportamento de DOM foi medido por
   Playwright, com a saída acima, mas o script vive no scratchpad da sessão.
