// Конфігурація Prisma CLI (Prisma 7 не читає .env автоматично).
import "dotenv/config";
import { defineConfig } from "prisma/config";

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
    seed: "tsx prisma/seed.ts",
  },
  datasource: {
    // process.env, а не env(): `prisma generate` має працювати і без DATABASE_URL
    // (наприклад, під час збирання Docker-образу).
    url: process.env.DATABASE_URL ?? "",
  },
});
