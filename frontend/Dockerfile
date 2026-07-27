# syntax=docker/dockerfile:1

# Node.js 24 — Active LTS atual (Next.js 16 exige >= 20.9)
FROM node:24-alpine

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000

# next dev com Turbopack habilita hot-reload; o código fonte é montado como volume em dev
CMD ["npm", "run", "dev"]
