/**
 * Приклад початкового наповнення каталогу.
 *
 * ⚠️ Це ДЕМОНСТРАЦІЙНІ дані: ціни, залишки та стан — приклад. Перед запуском магазину
 * замініть їх реальними товарами (через /addproduct у боті або відредагувавши цей файл).
 * Характеристики, яких ви не знаєте напевно, залишайте порожніми (null) — бот чесно
 * покаже покупцю «не вказано» і запропонує уточнити в продавця.
 *
 * Запуск: npm run db:seed          — додає товари, лише якщо каталог порожній
 *         npm run db:seed -- --force — додає приклади навіть у непорожній каталог
 */
import "dotenv/config";
import { createPrismaClient, Prisma } from "../src/database/client.js";
import type { BoxState, Completeness, ProductCondition } from "../src/generated/prisma/client.js";

interface SeedProduct {
  name: string;
  setNumber: string | null;
  theme: string;
  pieces: number | null;
  ageMin: number | null;
  price: string;
  stock: number;
  condition: ProductCondition;
  boxState: BoxState;
  completeness: Completeness;
  conditionNote?: string;
  description?: string;
}

const PRODUCTS: SeedProduct[] = [
  {
    name: "Bugatti Bolide",
    setNumber: "42151",
    theme: "LEGO Technic",
    pieces: 905,
    ageMin: 9,
    price: "1800",
    stock: 5,
    condition: "NEW",
    boxState: "ORIGINAL",
    completeness: "COMPLETE",
    description: "Модель гіперкара Bugatti Bolide з двигуном W16 і рухомими поршнями.",
  },
  {
    name: "Ford Mustang Shelby GT500",
    setNumber: "42138",
    theme: "LEGO Technic",
    pieces: 544,
    ageMin: 9,
    price: "2200",
    stock: 2,
    condition: "NEW",
    boxState: "ORIGINAL",
    completeness: "COMPLETE",
  },
  {
    name: "Express Passenger Train",
    setNumber: "60337",
    theme: "LEGO City",
    pieces: 764,
    ageMin: 7,
    price: "2400",
    stock: 3,
    condition: "NEW",
    boxState: "ORIGINAL",
    completeness: "COMPLETE",
  },
  {
    name: "Millennium Falcon",
    setNumber: "75257",
    theme: "LEGO Star Wars",
    pieces: 1351,
    ageMin: 9,
    price: "3500",
    stock: 1,
    condition: "USED",
    boxState: "NONE",
    completeness: "COMPLETE",
    conditionNote: "Зібраний один раз, інструкція є, наліпки наклеєно.",
  },
  {
    name: "Hogwarts Castle and Grounds",
    setNumber: "76419",
    theme: "LEGO Harry Potter",
    pieces: 2660,
    ageMin: 18,
    price: "4200",
    stock: 1,
    condition: "NEW",
    boxState: "DAMAGED",
    completeness: "COMPLETE",
    conditionNote: "Пом’ятий кут коробки, пакети з деталями запечатані.",
  },
  {
    name: "Galaxy Explorer",
    setNumber: "10497",
    theme: "LEGO Icons",
    pieces: 1254,
    ageMin: 18,
    price: "3900",
    stock: 0,
    condition: "NEW",
    boxState: "ORIGINAL",
    completeness: "COMPLETE",
  },
  {
    // Приклад товару з невідомими характеристиками
    name: "Поліцейська дільниця",
    setNumber: null,
    theme: "LEGO City",
    pieces: null,
    ageMin: null,
    price: "900",
    stock: 1,
    condition: "USED",
    boxState: "NONE",
    completeness: "INCOMPLETE",
    conditionNote: "Бракує двох мініфігурок, інструкції немає.",
  },
];

async function main(): Promise<void> {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL не задано");
  const prisma = createPrismaClient({ url, poolSize: 2 });
  try {
    const force = process.argv.includes("--force");
    const existing = await prisma.product.count();
    if (existing > 0 && !force) {
      console.log(`У каталозі вже є ${existing} товарів — приклади не додано (використайте --force).`);
      return;
    }
    for (const p of PRODUCTS) {
      await prisma.$transaction(async (tx) => {
        const product = await tx.product.create({
          data: {
            name: p.name,
            setNumber: p.setNumber,
            theme: p.theme,
            pieces: p.pieces,
            ageMin: p.ageMin,
            price: new Prisma.Decimal(p.price),
            stockOnHand: p.stock,
            condition: p.condition,
            boxState: p.boxState,
            completeness: p.completeness,
            conditionNote: p.conditionNote ?? null,
            description: p.description ?? null,
          },
        });
        await tx.productChange.create({
          data: { productId: product.id, field: "created", newValue: `${product.name} (seed)` },
        });
        if (p.stock > 0) {
          await tx.stockMovement.create({
            data: {
              productId: product.id,
              type: "INITIAL",
              onHandDelta: p.stock,
              reservedDelta: 0,
              onHandAfter: p.stock,
              reservedAfter: 0,
              actorType: "SYSTEM",
              note: "Початкове наповнення каталогу (seed)",
            },
          });
        }
      });
      console.log(`+ ${p.theme}${p.setNumber ? ` ${p.setNumber}` : ""} «${p.name}» — ${p.price} грн, ${p.stock} шт.`);
    }
    console.log(`Готово: додано ${PRODUCTS.length} демонстраційних товарів.`);
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
