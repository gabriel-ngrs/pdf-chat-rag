# Camada de dependências, compartilhada pelo build de produção e pelo modo de
# desenvolvimento. Invalida só quando o package.json ou o lock mudam.
#
# npm ci exige o package-lock.json commitado e instala exatamente o que ele fixa.
FROM node:22-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# ── Desenvolvimento: servidor do Vite, com HMR ───────────────────────────────
#
# Só é construído com `target: dev` (veja `docker-compose.dev.yml`); um
# `docker compose up --build` sem override nunca chega aqui, porque o estágio
# final desta imagem é o nginx lá embaixo.
#
# Não copia o código: ele chega por bind mount, que é o que faz uma edição no
# host virar recarga no navegador. O `node_modules` instalado acima é
# preservado por um volume anônimo — sem ele, o mount do host apagaria a
# instalação feita para a arquitetura do container.
FROM deps AS dev

EXPOSE 5173

CMD ["npm", "run", "dev"]

# ── Build de produção ────────────────────────────────────────────────────────
FROM deps AS build

COPY . .
RUN npm run build

# ── Produção: nginx servindo o build estático ────────────────────────────────
#
# Último estágio de propósito: é o que `docker build` escolhe sem `--target`, e
# é o que sustenta o "clone limpo + docker compose up --build" do README.
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
