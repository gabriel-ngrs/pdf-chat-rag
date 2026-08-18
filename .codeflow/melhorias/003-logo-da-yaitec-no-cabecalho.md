---
id: MELH-003
titulo: "Exibir a logo da Yaitec ao lado da marca TalkDoc"
solicitado_em: 2026-08-17
solicitado_por: owner
tipo: identidade visual
area: frontend
prioridade: média
esforco: baixo
status: bloqueado — falta o arquivo da logo
fase_dona: B.2 (app-shell)
---

# MELH-003 — A logo da Yaitec ao lado do TalkDoc

## O pedido

Colocar a logo da Yaitec na página, ao lado de "TalkDoc".

## O que existe hoje

A marca é tipográfica, montada em código — não há imagem nenhuma no projeto:

```tsx
// frontend/src/components/AppShell.tsx:59
function Wordmark() {
  return (
    <span className="font-display text-wordmark leading-none tracking-normal">
      Talk
      <span className="bg-highlight text-highlight-foreground rounded-xs px-1 py-0.5">Doc</span>
    </span>
  )
}
```

O marca-texto âmbar sobre "Doc" é a identidade inteira em um gesto — e é a mesma
cor que marca a citação no chat. Isso é relevante para esta melhoria: a logo da
Yaitec vai conviver com um lockup que já tem uma cor forte.

Não existe `frontend/public/`, não existe `frontend/src/assets/`, e o
`index.html` não declara favicon. Nenhum arquivo de imagem está versionado fora
das capturas de tela das avaliações.

## Bloqueio

**Não temos o arquivo.** O `Exemplo-YAITEC.pdf` foi inspecionado com `pypdf` e
não contém nenhuma imagem embutida nas três páginas — o logo não sai de lá.

O owner precisa fornecer, de preferência nesta ordem:

1. **SVG** — é o formato certo. Escala sem perda, herda cor por `currentColor`
   se o traço for único, e pesa menos que qualquer PNG.
2. PNG com fundo transparente, em @2x, se o SVG não existir.

Se a logo tiver versões clara e escura, **as duas** são necessárias: o produto
tem dois temas, e uma logo de tinta preta some no tema escuro.

## O que fazer quando o arquivo chegar

**Relação entre as marcas.** Precisa ficar claro o que a Yaitec é aqui: dona do
produto, cliente, ou autor do desafio. Isso decide a forma:

- se for **dona/autora**, o padrão é `TalkDoc` à esquerda, separador vertical
  fino, logo da Yaitec menor à direita, com texto acessível "por Yaitec";
- se for **cliente**, o lugar convencional é o rodapé, não o cabeçalho.

**Recomendação:** cabeçalho, à direita do wordmark, separada por um `1px` da cor
`--border` (o sistema já resolve profundidade por borda, não por sombra), com a
logo em altura menor que o wordmark. Duas marcas do mesmo tamanho brigam; a
hierarquia precisa dizer qual é o produto.

**Implementação:**

- SVG inline como componente React (não `<img>`), para poder herdar `currentColor`
  e responder ao tema sem carregar dois arquivos;
- se for `<img>`, `alt="Yaitec"` — nunca `alt=""`, porque a marca é informação;
- se a logo for link para o site da Yaitec, `rel="noreferrer"` e `target="_blank"`;
- altura fixa em token da escala de espaçamento, largura `auto`;
- o cabeçalho tem `h-14` — a logo não pode empurrar essa altura.

**Enquanto isso, o favicon.** Hoje não há nenhum, e o navegador mostra o ícone
genérico. Com o SVG em mãos, sai de graça — e é o tipo de detalhe que aparece na
primeira impressão de uma demonstração.

## Critérios de aceite

- [ ] Logo visível no cabeçalho, ao lado do wordmark, em ambos os temas, sem
      perda de contraste.
- [ ] A hierarquia deixa claro que o produto é o TalkDoc.
- [ ] Texto alternativo presente e correto.
- [ ] O cabeçalho continua com `h-14` e não quebra em 360 px de largura.
- [ ] Favicon declarado no `index.html`.
- [ ] `make check` verde.
