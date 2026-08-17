---
spec: 01-ingestao-pdf
fase: B.4
slug_fase: processing-status
tentativa: 2
veredito: APROVADO
score: 9.6
threshold: 8.5
range_avaliado: f00210e..3be5eed
---

# FASE B.4 — Avaliação independente (tentativa 2)

## 1. Veredito e score

**Veredito:** APROVADO · **Score:** 9.6 / threshold 8.5

Zero BLOQUEANTES, zero IMPORTANTES. Os três achados da tentativa 1 estão
fechados, e o mais importante deles foi fechado **na fonte**, não no chamador —
que era exatamente a crítica.

O que mais vale registrar: o `contrato_4_5` que eu tinha nomeado como o risco
concreto por trás do bloqueante foi medido contra o backend real e voltou
**exato** — os sete campos da §4.5, nenhum faltando, nenhum sobrando, e
`chunks_total` chegando `null` antes do chunking, como a fase assumia desde o
começo. A §4.5 funcionou como fonte única, que era a aposta do risco 7 da spec.

Sobre a elegibilidade formal (`A.4` ainda em `RESSALVAS`): a análise está na
avaliação da `B.3`, §2, e vale igual aqui. Em resumo — nenhum dos dois achados
IMPORTANTES da `A.4` toca o contrato que esta fase consome, e eu li o payload
cru em vez de presumir.

## 2. Scorecard

| # | Dimensão | Peso | Nota (0–5) | Evidência (arquivo:linha ou saída) |
|---|----------|------|------------|------------------------------------|
| 1 | Conformidade com a fase — ACs e escopo travado | 3 | 5 | **Contra o backend real:** ciclo `Lendo o documento → Pronto` sem reload; payload `processing 0/null` → `ready 10/10 page_count 3`; contrato §4.5 exato; polling parou em terminal (2 chamadas, ainda 2 após 6 s); menor intervalo 1,51 s; F5 retomou em "Pronto"; reset limpou o `localStorage` e voltou ao envio. **Com sequência controlada:** barra determinada com `aria-valuenow` 0 → 33 → 67 e legenda "8 de 12 trechos". Escopo travado intacto |
| 2 | Arquitetura e direção de dependências | 3 | 5 | `resolveView` (`ProcessingStatus.tsx:46-92`) é função pura que concentra a decisão de estado; o hook segue isolado; nenhuma chamada de rede fora do `api.ts` |
| 3 | Segurança / LGPD / multi-tenant | 3 | 5 | `failed` exibe a `error_message` do backend palavra por palavra e nada mais — medido nos dois temas: "O limite de uso da IA foi atingido. Tente de novo em alguns minutos." Nenhuma stack trace, nenhum corpo bruto, nenhum `code` cru. `grep` de segredo = 0 |
| 4 | Reusar/espelhar, não duplicar | 3 | 5 | `describeError('nao_encontrado')` reusado; `Progress`, `Skeleton`, `Badge`, `Button` do design system; a duplicação dos dois botões de reenvio virou um, com a `variant` decidida em `resolveView` |
| 5 | Padrões de domínio/aplicação | 2 | 5 | Os quatro estados de FR-9 num `Record` tipado; terminal e transitório continuam separados com o porquê registrado |
| 6 | Local e nomes dos arquivos | 2 | 5 | `progress.test.tsx` ao lado do primitivo que ele protege; `useDocumentStatus.test.ts` cresceu no lugar certo. `document` deixou de sombrear o global (`doc` no componente, `detail` no hook) |
| 7 | Qualidade de código | 2 | 4 | O card estável (uma única `Card` do primeiro render ao estado terminal) é a solução certa para a live region, e o comentário explica por quê. Desconto pela inconsistência do clamp monotônico, que reproduzi — ver §5.1 |
| 8 | Testes e cobertura | 2 | 4 | 7 testes de polling com `vi.useFakeTimers()` + 3 de regressão do primitivo, todos dentro do `make check`. Desconto: os quatro estados renderizados seguem sem teste de componente, agora que a testing-library está no projeto e custaria pouco |
| 9 | Migration safety (se aplicável) | 2 | — | Não se aplica |

Média ponderada (dimensões 1–8, peso total 20): 96/20 = 4,8 → **9,6/10**.

## 3. Achados BLOQUEANTES

Nenhum.

**B-1 da tentativa 1 (ciclo não observado no compose) — FECHADO.** Rodei o ciclo
inteiro eu mesmo, no navegador, contra o compose real subido de volume vazio.
Saídas na §6.

## 4. Achados IMPORTANTES

Nenhum.

**I-1 (o `progress.tsx` descartava o `value`) — FECHADO NA FONTE.**
`progress.tsx:14` agora passa `value={value}` à `ProgressPrimitive.Root`, e os
`aria-valuenow` manuais saíram do chamador. Verifiquei que o efeito é o
esperado, com uma sequência controlada contra o bundle de produção:

```
{"valuenow": "0",  "valuetext": "0 de 12 trechos", "dataState": "loading", "dataValue": "0"}
{"valuenow": "33", "valuetext": "4 de 12 trechos", "dataState": "loading", "dataValue": "33"}
{"valuenow": "67", "valuetext": "8 de 12 trechos", "dataState": "loading", "dataValue": "67"}
```

`data-state` deixou de ficar travado em `indeterminate` e `data-value` passou a
existir — os dois sintomas que eu tinha listado como dívida do remendo. A decisão
de manter o `aria-valuetext` está certa: "8 de 12 trechos" diz mais a quem ouve
do que "67%".

E o teste de regressão (`progress.test.tsx`) é bem desenhado: afirma
`aria-valuenow`, `aria-valuemax`, `data-value` e os três `data-state`
(`loading`/`complete`/`indeterminate`), além do `transform` do indicador. Como o
defeito veio do gerador do shadcn, esse teste é a única coisa que impede o
próximo `npx shadcn add progress` de reintroduzi-lo em silêncio.

**I-2 (polling sem cobertura) — FECHADO.** Sete testes em
`useDocumentStatus.test.ts:51-166`, com `vi.useFakeTimers()` e `fetchDocument`
falso, cobrindo os três casos que eu tinha desenhado e mais quatro: parada em
`ready`, parada em `failed`, `nao_encontrado` terminal sem reagendar, falha de
rede mantendo o último estado e tentando de novo, ausência de timer órfão após
desmontar, piso de 1 s, e nenhuma consulta sem documento. Rodei: verdes.

## 5. Sugestões

1. **`ProcessingStatus.tsx:44-53` — o clamp monotônico deixa a barra e a legenda
   discordando.** `useMonotonicPercent` guarda o maior percentual já mostrado,
   mas `aria-valuetext` e a legenda continuam lendo `chunks_processed` cru.
   Reproduzi com uma sequência que regride 8 → 3 de 12:

   ```
   {"valuenow": "67", "valuetext": "3 de 12 trechos", "dataState": "loading"}
   ```

   A barra diz 67%, o texto diz 3 de 12 (25%), e a legenda na tela lê "3 de 12
   trechos · 67%". Quem ouve ou lê recebe duas respostas diferentes.

   Vale notar que o cenário provavelmente é **inalcançável**: o hook usa cadeia
   de `setTimeout`, então nunca há mais de uma requisição em voo e resposta fora
   de ordem não acontece — a justificativa original do clamp não se sustenta com
   o desenho atual. A saída limpa é uma das duas: guardar o *snapshot* inteiro
   mais avançado (contagens e percentual juntos, sempre coerentes), ou remover o
   clamp e confiar no AC-12, que já obriga o backend a ser monotônico. Não
   bloqueio porque o caminho não é atingível hoje.

2. **Os quatro estados renderizados seguem sem teste de componente** (o executor
   pergunta na §9.3 se eu insisto). **Não insisto** — o que entrou cobre o hook,
   a função pura e o primitivo, que é onde os defeitos reais apareceram, e eu
   verifiquei os três estados na tela, nos dois temas. Mas agora que a
   testing-library está no projeto, quatro asserções sobre `resolveView` (que é
   pura e testável sem DOM) custariam dez minutos e blindariam a mensagem de
   `failed`, que é a que mais importa.

3. **`resolveView` devolve JSX dentro do objeto de estado.** Funciona, e a função
   é pura. Se um dia virar teste unitário, comparar `ReactNode` é chato —
   devolver um discriminante (`tone: 'neutral' | 'success' | 'danger'`) e deixar
   o ícone no componente tornaria a função trivialmente testável.

4. **Retry de polling sem teto** — mantido como dívida consciente, e concordo
   com a decisão. Registrado nos dois relatórios.

5. **`AppShell.tsx:63` ainda usa `py-0.5`**, que a nova redação da escala de
   espaçamento (`index.css:35-39`) excusa só para `pt-0.5` "nos números em mono".
   É o padding do marca-texto sobre "Doc" — mesma natureza de alinhamento óptico.
   Uma palavra no comentário fecha.

## 6. Comandos rodados + saídas reais

```text
$ git merge-base --is-ancestor 3be5eed HEAD
3be5eed ancestor OK

# ciclo completo pelo navegador, contra o compose real (volume novo, A.4 na árvore)
$ python3 gate.py
{
 "antes_do_envio": "Exemplo-YAITEC.pdf | 254 KB | Clique ou arraste outro arquivo para trocar.",
 "amostras": [
  {"estado": "Lendo o documento", "valuenow": null, "skeleton": true,
   "descricao": "Lendo o documento | Cada página vira trechos consultáveis. Isso leva alguns segundos."},
  {"estado": "Pronto", "valuenow": null, "skeleton": false,
   "descricao": "Pronto | O documento está indexado e pode ser consultado."}
 ],
 "polling": {"n_ate_terminal": 2, "n_apos_6s": 2, "menor_intervalo_s": 1.51},
 "posts": ["http://localhost:5173/api/documents"],
 "id_em_storage": "65745776-fa91-42e3-ad8b-2d3c607c51f8",
 "contrato_4_5": {
   "campos": ["chunks_processed","chunks_total","error_message","filename","id",
              "page_count","status"],
   "faltando": [],        <- o risco que o B-1 nomeava
   "sobrando": []
 },
 "sequencia_payload": [
   {"status":"processing","page_count":null,"chunks_processed":0,"chunks_total":null,"error_message":null},
   {"status":"ready","page_count":3,"chunks_processed":10,"chunks_total":10,"error_message":null}
 ],
 "apos_f5": "Pronto",
 "apos_reset": {"storage": null, "voltou_ao_envio": true}
}

# barra determinada e clamp, com sequência controlada por interceptação
# (não consome quota; exercita o bundle de produção servido pelo nginx)
$ python3 barra.py     # sequência: (null,0) (12,0) (12,4) (12,8) (12,3) ready
 {"estado":"Lendo o documento","valuenow":null,"dataState":null,"skeleton":true}
 {"estado":"Lendo o documento","valuenow":"0", "valuetext":"0 de 12 trechos","dataState":"loading","dataValue":"0"}
 {"estado":"Lendo o documento","valuenow":"33","valuetext":"4 de 12 trechos","dataState":"loading","dataValue":"33"}
 {"estado":"Lendo o documento","valuenow":"67","valuetext":"8 de 12 trechos","dataState":"loading","dataValue":"67"}
 {"estado":"Lendo o documento","valuenow":"67","valuetext":"3 de 12 trechos","dataState":"loading","dataValue":"67"}
 {"estado":"Pronto","valuenow":null,"dataState":null,"skeleton":false}
   ^ regressão 8->3 do servidor: a barra segura os 67% (clamp funciona) mas o
     texto acompanha o valor cru — a inconsistência da sugestão 5.1

# os três estados renderizados, nos dois temas, a 375 px
$ python3 estados.py
 processing-light 20 pares, 0 reprovados, pior 7.17, overflow_x 0
 processing-dark  20 pares, 0 reprovados, pior 7.15, overflow_x 0
 ready-light      21 pares, 0 reprovados, pior 7.17, overflow_x 0
   texto: "Pronto | O documento está indexado e pode ser consultado. | Pronto para conversar"
 ready-dark       21 pares, 0 reprovados, pior 7.15, overflow_x 0
 failed-light     20 pares, 0 reprovados, pior 7.17, overflow_x 0
   texto: "Não deu para processar | O limite de uso da IA foi atingido. Tente de novo em alguns minutos."
 failed-dark      20 pares, 0 reprovados, pior 7.15, overflow_x 0

$ make check     # 119 backend (cobertura core 98.98%) + 40 frontend
MAKE_CHECK_EXIT=0
$ make security
MAKE_SECURITY_EXIT=0

$ grep -rniE "GEMINI_API_KEY|DATABASE_URL|/home/gabriel|AIza" frontend/src
(vazio)

$ git status --short
(vazio — árvore limpa ao final; derrubei o compose e o volume que subi)
```

## 7. Itens da fase / DoD não atendidos

Nenhum item da fase. O critério de conclusão — ciclo `upload → processando →
pronto` observável no compose e sobrevivendo a um `F5` — está cumprido e
verificado de forma independente.

**Pendências da FEAT-0001, não desta fase:**

- `A.1` a `A.4` seguem com `RESSALVAS` na tentativa 1 e sem rework nesta branch;
  pela §2.11.3 continuam reprovadas, e a spec não fecha enquanto isso.
- "Identificadores em inglês" (DoD global) — detalhe na avaliação da `B.2`, §5.1.
- Fragmento da `GEMINI_API_KEY` no histórico do git (commit pai de `34cb479`) —
  matéria do Track A, mas é decisão do owner rotacionar a chave antes de publicar.

## 8. Divergências entre o relatório e o código real

Nenhuma. Confrontei cada afirmação da §5 e da §6 do relatório com medição
própria e todas se sustentam, inclusive as duas mais delicadas:

- **"`valores_da_barra: []` com o `Exemplo-YAITEC.pdf`"** — o relatório explica
  que a janela determinada dura menos que um ciclo de polling com um PDF de 3
  páginas, e mostra a barra com um PDF de 18. **Confirmo o fenômeno:** no meu
  ciclo contra o backend real, a interface também foi de indeterminado direto
  para "Pronto", e a barra determinada só apareceu quando controlei a sequência.
  A nota do relatório é honesta e necessária — sem ela, a saída sozinha pareceria
  dizer que a barra determinada nunca aparece.
- **"a falha foi real e não simulada; o backend gravou `limite_de_uso`"** — não
  reproduzi a quota estourada (seria queimar quota de propósito), mas verifiquei
  o que a fase controla: o estado `failed` exibe a `error_message` do backend
  palavra por palavra, nos dois temas, e o texto medido é a frase do backend, não
  uma genérica.
