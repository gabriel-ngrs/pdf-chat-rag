---
data: 2026-09-10
titulo: "Auditoria de dependências do frontend na abertura do repositório"
tags: [seguranca, dependencias, entrega]
status: ativa
---

# Auditoria de dependências do frontend na abertura do repositório

## Contexto

`make security` estava vermelho: `npm audit --audit-level=high` acusava **duas
vulnerabilidades altas** (`js-yaml`, `fast-uri`) e quatro moderadas. Nenhuma
existia quando o projeto foi fechado — são avisos publicados depois, sobre
versões que o `package-lock.json` já trazia.

Antes de abrir o repositório isso precisava sair. Um README que anuncia
`make security` como gate e um `make security` que reprova é pior que não ter
gate nenhum.

## Onde as vulnerabilidades estavam

Todas em dependência **transitiva de ferramenta de desenvolvimento** — nenhuma
chega ao bundle que o nginx serve:

| pacote | chega por | severidade |
|---|---|---|
| `js-yaml` | `eslint` → `@eslint/eslintrc`; `shadcn` → `cosmiconfig` | alta |
| `fast-uri` | `shadcn` → `ajv` | alta |
| `qs` | `shadcn` → `@modelcontextprotocol/sdk` → `express` | moderada |
| `hono` | `shadcn` → `@modelcontextprotocol/sdk` | moderada |
| `@vitest/mocker` | `vitest` | moderada |

## Decisão 1 — `overrides` no `package.json`, não `npm audit fix`

`npm audit fix` **quebra** neste projeto: `TypeError: Cannot read properties of
null (reading 'edgesOut')`, dentro do `#loadPeerSet` do arborist (npm 10.9.4,
Node 22.21). Não é o lockfile corrompido — apagar `node_modules` e o lock e
rodar `npm install` do zero reproduz o mesmo erro.

No lugar, quatro `overrides` declarados, cada um na **mesma major** da versão
vulnerável, para não trocar comportamento de ferramenta por correção de aviso:

```json
"overrides": {
  "js-yaml":  "^4.3.2",
  "fast-uri": "^3.1.7",
  "qs":       "^6.16.0",
  "hono":     "^4.13.7"
}
```

Override é preferível ao `fix` aqui por outro motivo: ele fica escrito. Quem
abrir o `package.json` vê qual pacote foi forçado e por quê; um `audit fix` bem
sucedido não deixa rastro nenhum além de um lockfile diferente.

## Decisão 2 — `vitest` pinado em `4.1.10`, sem o circunflexo

Com `^4.1.10`, o `npm install` resolve para `4.1.11` e **é essa resolução que
derruba o arborist**: o peer set novo arrasta `@vitest/browser-playwright@5.0.0`
e o npm estoura no meio de `idealTree:node_modules/vitest`. Com `4.1.10` exato,
instala limpo.

Pin exato é dívida declarada, não solução: assim que o npm (ou o vitest)
corrigir, o certo é voltar ao circunflexo. Está registrado aqui para que a volta
seja possível sem arqueologia.

## O que ficou em aberto, de propósito

`@vitest/mocker` continua com aviso **moderado**. A única correção oferecida é
`npm audit fix --force`, que sobe o `vitest` de major e reencontra exatamente o
travamento da decisão 2.

Fica como está, e o motivo é proporcional: é a biblioteca de dublês **do próprio
runner de testes**, que não roda em produção, não toca entrada de usuário e não
entra no bundle. `make security` reprova em `high`, então o gate permanece
honesto — ele não está sendo afrouxado para aceitar isto; este achado nunca
esteve acima da linha.

## Verificação

`npm audit --audit-level=high` sem achado. `npm run test` 119 passando,
`npm run build` e `npm run lint` limpos. `make check` e `make security` verdes.
