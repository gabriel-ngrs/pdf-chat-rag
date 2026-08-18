---
id: MELH-001
titulo: "A resposta do chat é exibida como texto cru — Markdown do modelo aparece na tela"
solicitado_em: 2026-08-17
solicitado_por: owner
tipo: legibilidade / correção de renderização
area: frontend + prompt
prioridade: alta
esforco: médio
status: aberto
fase_dona: B.3 (chat-view) e A.2 (core-prompting)
---

# MELH-001 — A resposta chega em Markdown e a tela mostra os asteriscos

## O que o usuário vê hoje

Colado pelo owner, exatamente como saiu da tela:

```
Você perguntou:Do que trata este documento?
Resposta
O TalkDoc respondeu:

Este documento trata do planejamento e da produção de conteúdos audiovisuais
para a empresa "Core AI Systems". (...)

Os principais pontos abordados são:

*   **Estratégia de Conteúdo:** O documento define formatos de gravação (...)
*   **Diretrizes de Comunicação:** Há uma proibição explícita de citar (...)
```

Três problemas distintos aparecem nesse recorte, e vale separá-los porque a
correção de cada um mora em um lugar diferente.

### 1. O Markdown não é renderizado

O modelo devolve Markdown — `**negrito**`, listas com `*   `, às vezes títulos.
A UI imprime a string como veio:

```tsx
// frontend/src/components/MessageList.tsx:155
<div className={cn('max-w-prose whitespace-pre-wrap', refused && 'text-muted-foreground')}>
  {content}
</div>
```

`whitespace-pre-wrap` preserva as quebras de linha — que é o certo — mas nada
converte a sintaxe. O resultado é que a estrutura que o modelo produziu para
ajudar a leitura (negrito no rótulo do item, marcador na lista) vira ruído
visual: o leitor precisa filtrar asteriscos com o olho antes de ler a frase.

### 2. Nada dá hierarquia ao bloco

Mesmo sem Markdown, o parágrafo de resposta é uma parede de texto: um único
`<div>` com o conteúdo inteiro. Não há espaçamento entre parágrafos, nem
diferença entre a frase de abertura e a lista que a desenvolve. A resposta do
exemplo tem ~1.200 caracteres em bloco contínuo.

### 3. Os rótulos para leitor de tela vazam na cópia

`Você perguntou:` e `O TalkDoc respondeu:` são `sr-only`
(`MessageList.tsx:82` e `MessageList.tsx:147`) — corretos para acessibilidade,
invisíveis na tela. Mas eles entram no `Ctrl+C`, e é por isso que aparecem
grudados no texto colado acima (`Você perguntou:Do que trata...`). Quem copia
uma resposta para colar em outro lugar leva junto uma etiqueta que não pediu, e
sem nem um espaço separando.

## Causa raiz

Duas pontas, e a correção provavelmente precisa das duas:

**Frontend.** Não existe renderizador de Markdown no projeto. O `package.json`
do frontend não traz `react-markdown`, `marked` nem equivalente — a resposta
sempre foi tratada como texto simples porque, nas fases iniciais, ela era.

**Prompt.** `backend/app/core/prompt.py::ANSWER_INSTRUCTIONS` (linha 33) não diz
nada sobre formato de saída. As quatro instruções tratam de idioma, citação de
página, recusa e injeção de prompt. O formato fica por conta do modelo — e o
Gemini, sem instrução em contrário, formata em Markdown.

## Caminhos

### A. Renderizar o Markdown no frontend (recomendado)

Adicionar um renderizador e mapear cada elemento aos tokens do design system —
nunca ao estilo default da biblioteca, que ignoraria a escala tipográfica de
`index.css`.

- Biblioteca: `react-markdown` com `remark-gfm`. É a opção com menor superfície
  e sem `dangerouslySetInnerHTML`.
- **Restrição de segurança, não negociável:** o conteúdo vem de um modelo que
  leu um PDF de origem desconhecida. Renderizar HTML cru dali seria abrir XSS
  pela porta da frente. `react-markdown` sem `rehype-raw` já bloqueia HTML
  embutido — manter assim, e travar isso com um teste.
- Componentes mapeados: `p`, `strong`, `em`, `ul`/`ol`/`li`, `code`, `a`
  (com `rel="noreferrer"` e `target="_blank"`). Título (`h1`–`h6`) dentro de uma
  resposta de chat deve ser rebaixado a texto forte: um `<h2>` no meio da lista
  de mensagens quebra a árvore de cabeçalhos da página.
- Streaming: o texto chega token a token, então o Markdown fica **incompleto**
  na maior parte do tempo (`**Estratég` antes de fechar o negrito). Um parser
  reprocessando a string inteira a cada token é o custo previsível aqui — medir
  antes de aceitar, e considerar renderizar o stream como texto e só passar pelo
  Markdown quando o evento `done` chegar.

### B. Restringir o formato no prompt

Acrescentar a `ANSWER_INSTRUCTIONS` uma regra de formato: parágrafos curtos,
listas apenas quando a resposta for de fato uma enumeração, sem títulos, sem
negrito. Barato e determinístico? Não — é uma instrução, e instrução se obedece
"na maioria das vezes". Serve como **complemento** de (A), reduzindo a variedade
que o renderizador precisa cobrir, não como substituto.

Se essa alteração for feita, os testes de `prompt.py` que asseguram o conteúdo
de `ANSWER_INSTRUCTIONS` precisam acompanhar.

### C. Trabalhar a hierarquia do bloco de resposta

Independente do Markdown:

- espaço entre parágrafos (`space-y-3`), não só quebra de linha;
- manter a largura em `max-w-prose` (já está) — é o que segura a linha em ~72
  caracteres;
- separar visualmente a resposta das citações, que hoje encostam no texto.

### D. Consertar o vazamento da cópia

Trocar `Você perguntou: ` / `O TalkDoc respondeu:` por rótulos que não entrem na
seleção. O caminho mais limpo é `aria-label` no container em vez de `<span
class="sr-only">` — o leitor de tela continua anunciando, e o texto some do
`Ctrl+C`. Onde o `sr-only` for necessário mesmo, ele deve ficar fora do elemento
que contém o texto copiável.

## Relacionado

O [BUG-005](../bugs/005-resposta-cita-trecho-n-que-nao-existe-na-interface.md)
também é sobre o texto da resposta — ali o problema é o rótulo "Trecho N", que o
modelo cita e a tela não mostra. São defeitos diferentes no mesmo parágrafo, e
quem for mexer em `ANSWER_INSTRUCTIONS` deve resolver os dois na mesma passada,
para não reescrever o prompt duas vezes.

## Restrições do projeto que valem aqui

- Cor e tamanho de texto **sempre** por token semântico (regra do `index.css`).
  O renderizador de Markdown não pode trazer estilo próprio.
- Toda dependência nova passa por `npm audit --audit-level=high` (gate
  `security` do `manifest.md`).
- `tsc --strict` sobre `frontend/src` — o mapa de componentes precisa de tipos,
  não de `any`.

## Critérios de aceite

- [ ] Uma resposta com negrito e lista aparece formatada, sem nenhum asterisco
      visível na tela.
- [ ] HTML dentro da resposta do modelo é exibido como texto, nunca executado —
      com teste que prova isso.
- [ ] Copiar uma resposta e colar em um editor de texto não traz
      "O TalkDoc respondeu:" nem "Você perguntou:".
- [ ] O anúncio por leitor de tela continua funcionando (os testes de
      acessibilidade de `MessageList.test.tsx` seguem verdes).
- [ ] Durante o streaming, o texto não pisca nem reflui a cada token.
- [ ] `make check` verde.
