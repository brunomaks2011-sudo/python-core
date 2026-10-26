// Ручний перегляд діалогу: npx tsx tests/manual/transcript.ts
import "../helpers/setupEnv.js";
import { Telegram } from "telegraf";
import type { Update, UserFromGetMe } from "telegraf/types";
import { createBot } from "../../src/bot/bot.js";
import { createServices } from "../../src/services.js";
import { FakeTelegram, callbackUpdate, contactUpdate, textUpdate, type TestUser } from "../helpers/fakeTelegram.js";
import { ADMIN_ID, createProduct, migrateTestDb, resetDb, testConfig, testPrisma } from "../helpers/testDb.js";

const customer: TestUser = { id: 5551, first_name: "Олена" };
const owner: TestUser = { id: ADMIN_ID, first_name: "Власник" };

async function main() {
  migrateTestDb();
  const prisma = testPrisma();
  await resetDb(prisma);
  const fake = new FakeTelegram();
  const apiRoot = await fake.start();
  const config = testConfig();
  const services = createServices({ config, prisma, telegram: new Telegram(config.telegram.token, { apiRoot }), anthropic: null });
  const { bot } = createBot(services, { detach: false, apiRoot });
  bot.botInfo = { id: 1, is_bot: true, first_name: "B", username: "b" } as UserFromGetMe;
  await createProduct(prisma, { stock: 5 });
  await createProduct(prisma, { name: "Ford Mustang Shelby GT500", setNumber: "42138", price: "2200", stock: 2 });
  await createProduct(prisma, { name: "Galaxy Explorer", setNumber: "10497", theme: "LEGO Icons", price: "3900", stock: 0 });
  await createProduct(prisma, { name: "Поліцейська дільниця", setNumber: null, theme: "LEGO City", price: "900", stock: 1, pieces: null, ageMin: null, condition: "USED", boxState: "NONE", completeness: "INCOMPLETE" });

  let shown = 0;
  const step = async (label: string, u: Update) => {
    console.log(`\n\x1b[36m>>> ${label}\x1b[0m`);
    await bot.handleUpdate(u);
    for (const c of fake.calls.slice(shown)) {
      if (!["sendMessage", "sendPhoto", "editMessageText", "answerCallbackQuery"].includes(c.method)) continue;
      const who = Number(c.payload.chat_id) === ADMIN_ID ? "[ВЛАСНИК]" : "";
      const text = String(c.payload.text ?? c.payload.caption ?? "");
      const buttons = ((c.payload.reply_markup as any)?.inline_keyboard ?? []).flat().map((b: any) => `[${b.text}]`).join(" ");
      if (c.method === "answerCallbackQuery") { if (c.payload.text) console.log(`  (сповіщення: ${c.payload.text})`); continue; }
      console.log(`${who}${c.method === "editMessageText" ? "(ред.) " : ""}${text}${buttons ? `\n  ${buttons}` : ""}\n  ·`);
    }
    shown = fake.calls.length;
  };
  const btn = (prefix: string, which: "first" | "last" = "last") => { const b = fake.buttonsTo(customer.id, 8).filter((x) => x.startsWith(prefix)); return which === "first" ? b[0]! : b[b.length - 1]!; };

  await step("/start", textUpdate(customer, "/start"));
  await step("Привіт! Є LEGO Technic?", textUpdate(customer, "Привіт! Є LEGO Technic?"));
  await step("Чи є LEGO 10497?", textUpdate(customer, "Чи є LEGO 10497?"));
  await step("Що є до двох тисяч?", textUpdate(customer, "Що є до двох тисяч?"));
  await step("є вживані?", textUpdate(customer, "є вживані?"));
  await step("Хочу замовити 42151", textUpdate(customer, "Хочу замовити 42151"));
  await step("кількість", callbackUpdate(customer, btn("ck:q:", "first")));
  await step("ім'я", textUpdate(customer, "олена коваль"));
  await step("телефон (кнопка)", contactUpdate(customer, "380501112233"));
  await step("місто", textUpdate(customer, "Львів"));
  await step("відділення", textUpdate(customer, "5"));
  await step("оплата", callbackUpdate(customer, btn("ck:pay:", "first")));
  await step("підтвердити", callbackUpdate(customer, btn("ck:ok:")));
  await step("[власник] підтвердити", callbackUpdate(owner, "a:os:101:CONFIRMED"));
  await step("[власник] /order 101", textUpdate(owner, "/order 101"));
  await step("/myorders", textUpdate(customer, "/myorders"));
  await step("Скільки коштує цей лего?", textUpdate(customer, "Скільки коштує цей лего?"));
  await step("абракадабра", textUpdate(customer, "абракадабра"));
  await step("[власник] /stock", textUpdate(owner, "/stock"));
  await fake.stop();
  await prisma.$disconnect();
}
main().catch((e) => { console.error(e); process.exit(1); });
