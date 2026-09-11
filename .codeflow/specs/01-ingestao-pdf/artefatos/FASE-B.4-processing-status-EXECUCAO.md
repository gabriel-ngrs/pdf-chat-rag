---
spec: 01-ingestao-pdf
fase: B.4
slug_fase: processing-status
status: rework
tentativa: 2
reprovacoes: 1
sha_inicial: f00210e
sha_final: 3be5eed
range: f00210e..3be5eed
---

# FASE B.4 — Relatório de execução

> Executada no worktree `/home/gabriel/Projetos/pdf-chat-rag-trackB`, branch
> `feat/trackB-frontend`.

## ✅ Verificado contra o backend real na tentativa 2

Na tentativa 1 o ciclo foi observado contra um stub, o que gerou o BLOQUEANTE
B-1. Com o Track A mergeado em `dev`, esta tentativa rodou o ciclo inteiro
contra o backend da `A.4`, pelo `docker compose`, com `GEMINI_API_KEY` real.

O risco que o avaliador nomeou — "os nomes de campo foram validados contra um
stub que o próprio executor escreveu, o que confirma a leitura dele da spec, não
o comportamento do backend" — foi fechado lendo o payload cru do servidor: **os
sete campos da §4.5, nem um a mais, nem um a menos.** Saída na §5.

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
| `frontend/src/hooks/useDocumentStatus.test.ts` | `progressPercent` (o que ela recusa a inventar) e, na tentativa 2, o polling inteiro com relógio falso |
| `frontend/src/components/ui/progress.test.tsx` | *(tentativa 2)* Regressão da causa raiz do I-1: valor exposto ao leitor de tela e `data-state` correto |

## 3. Arquivos ALTERADOS

| Arquivo | O que mudou |
|---------|-------------|
| `frontend/src/App.tsx` | Troca o painel provisório da `B.3` pelo acompanhamento e acrescenta `handleReset` |
| `frontend/src/components/ui/progress.tsx` | *(tentativa 2)* Repassa o `value` à Root do primitivo — a causa raiz do I-1 |

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

# TENTATIVA 2 — contrato da §4.5 lido do backend real, através do nginx
$ python3 probe_contrato.py
POST /api/documents -> 202 {"id": "0285208b-6a57-48fb-9150-d0643ae059cc", "status": "pending"}

Campos devolvidos: ['chunks_processed', 'chunks_total', 'error_message',
                    'filename', 'id', 'page_count', 'status']
Faltando em relação à §4.5: nenhum
Além da §4.5: nenhum

Sequência observada:
  status=processing page_count=None chunks=0/None  error=None   <- janela indeterminada real
  status=processing page_count=3    chunks=0/10    error=None
  status=ready      page_count=3    chunks=10/10   error=None

chunks_processed monotônico: True
houve janela com chunks_total=None: True

# TENTATIVA 2 — barra determinada com dado real (PDF de 18 páginas, 180 trechos)
$ python3 probe_progress.py
{"titulo": "Lendo o documento", "role": "progressbar", "valuenow": "9",
 "label": "Progresso da leitura do documento", "legenda": "16 de 180 trechos · 9%"}
{"titulo": "Lendo o documento", "role": "progressbar", "valuenow": "27",
 "legenda": "48 de 180 trechos · 27%"}
{"titulo": "Lendo o documento", "role": "progressbar", "valuenow": "36",
 "legenda": "64 de 180 trechos · 36%"}
{"titulo": "Lendo o documento", "role": "progressbar", "valuenow": "44",
 "legenda": "80 de 180 trechos · 44%"}
{"titulo": "Não deu para processar"}   <- quota do free tier estourou; ver abaixo

# O `failed` acima é real, não simulado. Log do backend:
$ docker compose logs backend | grep document.failed | tail -1
{"code": "limite_de_uso",
 "message": "O limite de uso da IA foi atingido. Tente de novo em alguns minutos.",
 "event": "document.failed", "document_id": "42d4cfda-…", "level": "error"}

# gate da fase, contra o backend real
$ python3 audit_processing.py http://localhost:5173
{
  "transicoes": [
    {"titulo": "Enviando o arquivo…", "valorBarra": null, "barraIndeterminada": false},
    {"titulo": "Lendo o documento",   "valorBarra": null, "barraIndeterminada": true},
    {"titulo": "Pronto",              "valorBarra": null, "barraIndeterminada": false}
  ],
  "chegou_em_pronto": true,
  "progresso_monotonico": true,
  "valores_da_barra": [],
  "teve_janela_indeterminada": true,
  "menor_intervalo_de_polling_s": 1.57,
  "polling_parou_em_pronto": true,
  "apos_f5": "Pronto",
  "aria": {"roleStatusPresente": true, "textoAnunciado": "Pronto"},
  "falha": {"titulo": "Não deu para processar"},
  "reset_volta_ao_envio": true,
  "reset_limpou_storage": null
}

# regressão da causa raiz do progress.tsx, agora versionada e offline
$ npm run test -- progress
✓ expõe o valor ao leitor de tela, não só ao pixel
    aria-valuenow="40"  aria-valuemax="100"  data-value="40"
✓ distingue em progresso, completo e indeterminado no data-state
    value=40 -> data-state="loading";  value=100 -> "complete";  sem value -> "indeterminate"
✓ desenha o indicador na proporção do valor
```

> Nota honesta sobre `valores_da_barra: []` acima: com o `documento-de-exemplo.pdf`
> (3 páginas, 10 trechos, um único lote de embeddings) a janela determinada dura
> menos que um ciclo de polling de 1,5 s, então a interface vai de indeterminado
> direto para `Pronto`. O comportamento está certo — a barra determinada existe e
> foi observada com o PDF de 18 páginas logo acima, com `valuenow` 9 → 27 → 36 →
> 44 e a legenda "16 de 180 trechos". Registro os dois porque o primeiro, sozinho,
> pareceria dizer que a barra determinada nunca aparece.

## 6. Critérios de aceite da fase (com evidência)

- [x] **AC-22** — transição `enviando → na fila → lendo → pronto` observada numa
  única sessão de página, sem `reload` entre as amostras.
- [x] **AC-12** — contra o backend real: `chunks_processed` sobe `0 → 10` no
  payload e `aria-valuenow` sobe `9 → 27 → 36 → 44` na tela, com a legenda
  "16 de 180 trechos", "48 de 180 trechos"… Ordem crescente nas duas medições.
- [x] **AC-5 (lado da UI)** — documento `failed` exibe a `error_message` do
  backend palavra por palavra. Na tentativa 2 a falha foi real e não simulada: o
  PDF de 18 páginas estourou a quota do free tier, o backend gravou
  `code: limite_de_uso` com mensagem em pt-BR, e foi essa frase que apareceu na
  tela.
- [x] **Contrato da §4.5** — o payload real traz exatamente os sete campos, sem
  faltar nem sobrar, e `chunks_total` chega `null` antes do chunking, como a
  fase assumia. Era o risco nomeado no B-1 da avaliação.
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
- [x] **Critério de conclusão da fase** — ciclo `upload → processando → pronto`
  observado **no `docker compose`** com a `A.4`, sobrevivendo a um `F5`.

## 7. Definition of Done da fase

- [x] Testes da fase verdes (11 nesta fase, 40 no frontend, 119 no backend)
- [x] `make check` inteiro retorna zero; `make security` zero
- [x] Escopo travado respeitado: polling de 1,5 s (nunca abaixo de 1 s), timer
  limpo no cleanup, nenhum progresso inventado, nenhuma stack trace ou corpo
  bruto exibido
- [x] Nenhum segredo/PII em log, DTO ou exceção
- [x] Commits em pt-BR (Conventional Commits)

## 8. (Em rework) O que mudou nesta tentativa

Avaliação da tentativa 1: **REPROVADO**, score 8,6. Um BLOQUEANTE, dois
IMPORTANTES e cinco sugestões.

### B-1 — ciclo não observado no compose → **corrigido**

Track A mergeado em `dev`; ciclo rodado contra a `A.4` real, incluindo a leitura
crua do payload que fechou o risco de divergência de nomes de campo. §5.

### I-1 — `progress.tsx` descartava o `value` → **corrigido na fonte**

O diagnóstico do avaliador estava certo, e a crítica à correção também: a
tentativa 1 remendou no chamador, deixando `data-state="indeterminate"` a 67% e
a armadilha montada para o próximo consumidor. Agora `value` é repassado à
`ProgressPrimitive.Root` (uma linha), os `aria-valuenow` manuais saíram de
`ProcessingStatus.tsx`, e o `aria-valuetext` ficou — porque "8 de 12 trechos"
diz mais do que "67%", como o próprio avaliador observou.

Acrescentei `src/components/ui/progress.test.tsx` para a causa raiz não voltar:
afirma `aria-valuenow`, `data-value` e os três `data-state`
(`loading`/`complete`/`indeterminate`). Sem esse teste, o mesmo defeito volta na
próxima vez que alguém rodar o CLI do shadcn.

### I-2 — nenhum teste versionado cobre o polling → **corrigido**

Sete testes novos em `useDocumentStatus.test.ts`, com `vi.useFakeTimers()` e
`fetchDocument` falso, exatamente os três que o avaliador desenhou mais quatro:
parada em `ready`, parada em `failed`, `nao_encontrado` terminal sem reagendar,
falha de rede mantendo o último estado e reagendando, ausência de timer órfão
após desmontar, piso de 1 s entre consultas, e nenhuma consulta sem documento.

### Sugestões acatadas

- **S-1, `document` sombreando o global do DOM** — renomeado para `doc` no
  componente e para `detail` dentro do hook.
- **S-2, dois blocos quase idênticos do botão de reenvio** — viraram um, com a
  `variant` decidida por `resolveView`.
- **S-3, `role="status"` remontado na transição do esqueleto** — o card agora é
  sempre o mesmo elemento, do primeiro render ao estado terminal, então a live
  region nunca é reinserida e a primeira mudança de estado é anunciada.

### Sugestões avaliadas e não acatadas

- **S-4, retry de rede sem teto.** Mantido. O avaliador registrou que é coerente
  com "falha de rede não derruba o estado" e que não incomoda numa entrega
  local; acrescentar backoff aqui seria ampliar escopo de rework. Fica anotado
  como dívida consciente.
- **S-5, intervalo de 1,5 s** — o avaliador concordou com o número. Sem mudança.

## 9. Itens em aberto / dúvidas para o avaliador

1. **Retry de polling sem teto** (S-4 acima) — dívida consciente, não esquecimento.
2. **`ready` não leva a lugar nenhum ainda** — o sinal é o selo "Pronto para
   conversar". A `FEAT-0002 B.1` é quem transforma isso em entrada de conversa.
3. **Os quatro estados não têm teste de componente**; o que entrou versionado
   cobre o hook de polling, o `progressPercent` e o primitivo de barra. A
   renderização dos estados foi medida por Playwright contra o compose real, com
   as saídas na §5. Se o avaliador quiser os quatro estados em teste de
   componente, o caminho já está pavimentado — a testing-library entrou no
   projeto nesta tentativa.
4. **A quota do free tier é real e aparece.** Um PDF de 18 páginas (180 trechos)
   estoura o limite de 100 requisições/minuto e termina em `failed` com
   `limite_de_uso`. A interface trata isso corretamente, mas é bom o owner saber
   que o teto prático de demonstração é bem abaixo das 20 páginas da spec.
