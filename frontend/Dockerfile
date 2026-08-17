FROM node:22-alpine AS build

WORKDIR /app

# npm ci exige o package-lock.json commitado e instala exatamente o que ele fixa.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
