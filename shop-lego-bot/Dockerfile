# syntax=docker/dockerfile:1

# ── Базовий образ: Node.js 22 LTS + OpenSSL (потрібен рушію міграцій Prisma) ──
FROM node:22-bookworm-slim AS base
RUN apt-get update \
  && apt-get install -y --no-install-recommends openssl ca-certificates \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# ── Збирання: встановлення всіх залежностей, генерація Prisma Client, компіляція TypeScript ──
FROM base AS build
COPY package.json package-lock.json ./
RUN npm ci
COPY prisma ./prisma
COPY prisma.config.ts tsconfig.json tsconfig.build.json ./
COPY src ./src
RUN npm run build

# ── Робочий образ: лише продакшн-залежності та скомпільований код ──
FROM base AS runtime
ENV NODE_ENV=production
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist
# Вихідний код (з уже згенерованим Prisma Client) потрібен для наповнення каталогу: npx prisma db seed
COPY --from=build /app/src ./src
COPY prisma ./prisma
COPY prisma.config.ts ./
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
# Прибираємо Windows-переноси рядків (CRLF), якщо проєкт клонували у Windows
RUN sed -i 's/\r$//' scripts/docker-entrypoint.sh
USER node
EXPOSE 8080
# Під час старту застосовуються міграції, потім запускається бот (PID 1 отримує SIGTERM).
ENTRYPOINT ["sh", "scripts/docker-entrypoint.sh"]
