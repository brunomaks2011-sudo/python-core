# syntax=docker/dockerfile:1
# Багатоетапна збірка «Цеглинки». Цілі:
#   runner — легкий production-образ (Next.js standalone)
#   tools  — повний набір залежностей для міграцій і seed

FROM node:22-alpine AS base
RUN apk add --no-cache libc6-compat openssl
WORKDIR /app

# ---------- Залежності ----------
FROM base AS deps
COPY package.json package-lock.json ./
COPY prisma ./prisma
RUN npm ci

# ---------- Збірка ----------
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_OUTPUT=standalone
# NEXT_PUBLIC_* «вшиваються» в клієнтський бандл під час збірки
ARG NEXT_PUBLIC_SITE_URL=http://localhost:3000
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
RUN npx prisma generate && npx next build

# ---------- Інструменти: міграції / seed ----------
FROM builder AS tools
CMD ["npx", "prisma", "migrate", "deploy"]

# ---------- Production ----------
FROM base AS runner
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0 UPLOAD_DIR=/app/uploads
RUN addgroup -S -g 1001 nodejs && adduser -S -u 1001 -G nodejs nextjs \
  && mkdir -p /app/uploads && chown nextjs:nodejs /app/uploads
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD wget -qO- http://127.0.0.1:3000/robots.txt >/dev/null || exit 1
CMD ["node", "server.js"]
