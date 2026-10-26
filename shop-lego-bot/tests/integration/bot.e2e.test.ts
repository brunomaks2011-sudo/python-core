import "../helpers/setupEnv.js";
import assert from "node:assert/strict";
import { after, before, beforeEach, describe, it } from "node:test";
import { Telegram, type Telegraf } from "telegraf";
import type { Update, UserFromGetMe } from "telegraf/types";
import { createBot } from "../../src/bot/bot.js";
import type { BotContext } from "../../src/bot/context.js";
import type { PrismaClient } from "../../src/database/client.js";
import { createServices, type Services } from "../../src/services.js";
import {
  FakeTelegram,
  callbackUpdate,
  contactUpdate,
  photoUpdate,
  textUpdate,
  type TestUser,
} from "../helpers/fakeTelegram.js";
import { ADMIN_ID, createProduct, migrateTestDb, resetDb, testConfig, testPrisma } from "../helpers/testDb.js";

let fake: FakeTelegram;
let prisma: PrismaClient;
let services: Services;
let bot: Telegraf<BotContext>;

const customer: TestUser = { id: 5551, first_name: "Олена", username: "olena" };
const owner: TestUser = { id: ADMIN_ID, first_name: "Власник" };

async function send(update: Update): Promise<void> {
  await bot.handleUpdate(update);
}

const joined = (chatId: number) => fake.messagesTo(chatId).join("\n---\n");

function button(chatId: number, prefix: string, which: "first" | "last" = "last"): string {
  const found = fake.buttonsTo(chatId, 8).filter((b) => b.startsWith(prefix));
  assert.ok(found.length > 0, `кнопку «${prefix}…» не знайдено серед: ${fake.buttonsTo(chatId, 8).join(", ")}`);
  return which === "first" ? found[0]! : found[found.length - 1]!;
}

async function stockOf(productId: number) {
  const p = await prisma.product.findUniqueOrThrow({ where: { id: productId } });
  return { onHand: p.stockOnHand, reserved: p.stockReserved };
}

before(async () => {
  migrateTestDb();
  prisma = testPrisma();
  fake = new FakeTelegram();
  const apiRoot = await fake.start();
  const config = testConfig();
  const telegram = new Telegram(config.telegram.token, { apiRoot });
  services = createServices({ config, prisma, telegram, anthropic: null });
  ({ bot } = createBot(services, { detach: false, apiRoot }));
  bot.botInfo = {
    id: 123456789,
    is_bot: true,
    first_name: "Test LEGO Bot",
    username: "test_lego_bot",
    can_join_groups: false,
    can_read_all_group_messages: false,
    supports_inline_queries: false,
  } as UserFromGetMe;
});

after(async () => {
  await services.broadcasts.stop();
  await fake.stop();
  await prisma.$disconnect();
});

beforeEach(async () => {
  await resetDb(prisma);
  fake.clear();
});

/** Проводить покупця через усе оформлення до підсумку. */
async function checkoutToSummary(productId: number): Promise<void> {
  await send(callbackUpdate(customer, `buy:${productId}`));
  await send(callbackUpdate(customer, button(customer.id, "ck:q:", "first")));
  await send(textUpdate(customer, "Олена Коваль"));
  await send(contactUpdate(customer, "+380501112233"));
  await send(textUpdate(customer, "Львів"));
  await send(textUpdate(customer, "5"));
  await send(callbackUpdate(customer, button(customer.id, "ck:pay:").replace(/:\w+$/, ":cod")));
}

describe("покупець: пошук, перевірка наявності та замовлення", () => {
  it("повний сценарій із технічного завдання", async () => {
    const technic = await createProduct(prisma, { stock: 5 });
    await createProduct(prisma, { name: "Ford Mustang Shelby GT500", setNumber: "42138", price: "2200", stock: 2 });
    await createProduct(prisma, { name: "Express Passenger Train", setNumber: "60337", theme: "LEGO City", price: "2400", stock: 3 });

    await send(textUpdate(customer, "/start"));
    assert.match(joined(customer.id), /Вітаю, Олена! 👋/);

    fake.clear();
    await send(textUpdate(customer, "Привіт! Є LEGO Technic?"));
    let out = joined(customer.id);
    assert.match(out, /Вітаю! 👋 Так, у нас є набори LEGO Technic!/);
    assert.match(out, /LEGO Technic 42151 «Bugatti Bolide» — <b>1 800 грн<\/b>/);
    assert.match(out, /LEGO Technic 42138 «Ford Mustang Shelby GT500» — <b>2 200 грн<\/b>/);
    assert.doesNotMatch(out, /60337/, "показуються лише набори запитаної тематики");
    assert.match(out, /Ціни та наявність перевірено за каталогом магазину/);

    fake.clear();
    await send(textUpdate(customer, "Чи є LEGO 42151?"));
    out = joined(customer.id);
    assert.match(out, /Так, <b>LEGO Technic 42151 «Bugatti Bolide»<\/b> є в наявності!/);
    assert.match(out, /Ціна: <b>1 800 грн<\/b>/);
    assert.match(out, /В наявності: 5 шт\./);
    assert.match(out, /Бажаєте оформити замовлення\?/);

    fake.clear();
    await checkoutToSummary(technic.id);
    out = joined(customer.id);
    assert.match(out, /ім’я та прізвище/);
    assert.match(out, /номер телефону/);
    assert.match(out, /Телефон збережено/);
    assert.match(out, /Перевірте, будь ласка, замовлення/);
    assert.match(out, /Номер набору LEGO: 42151/);
    assert.match(out, /Кількість: 1 набір/);
    assert.match(out, /Ціна за одиницю: 1 800 грн/);
    assert.match(out, /Загальна вартість: 1 800 грн/);
    assert.match(out, /Отримувач: Олена Коваль/);
    assert.match(out, /Телефон: \+380501112233/);
    assert.match(out, /Доставка: Львів, Відділення №5/);
    assert.match(out, /Оплата: Накладений платіж/);
    const confirm = button(customer.id, "ck:ok:");
    assert.ok(fake.buttonsTo(customer.id, 1).some((b) => b.startsWith("ck:edit:")), "є кнопка «Змінити дані»");
    assert.ok(fake.buttonsTo(customer.id, 1).some((b) => b.startsWith("ck:x:")), "є кнопка «Скасувати замовлення»");

    fake.clear();
    await send(callbackUpdate(customer, confirm));
    out = joined(customer.id);
    assert.match(out, /Дякуємо за замовлення! 🎉/);
    assert.match(out, /Номер замовлення: <b>№101<\/b>/);
    assert.match(out, /Товар: LEGO Technic 42151 «Bugatti Bolide»/);
    assert.match(out, /Кількість: 1 набір/);
    assert.match(out, /Вартість: <b>1 800 грн<\/b>/);
    assert.match(out, /Статус: очікує підтвердження магазину\./, "статус відповідає реальному стану в БД");
    assert.match(joined(owner.id), /Нове замовлення №101/, "власник отримав сповіщення");
    assert.deepEqual(await stockOf(technic.id), { onHand: 5, reserved: 1 });
    const order = await prisma.order.findUniqueOrThrow({ where: { id: 101 } });
    assert.equal(order.status, "AWAITING_CONFIRMATION");

    fake.clear();
    await send(callbackUpdate(customer, confirm));
    assert.match(joined(customer.id), /вже оформлено: <b>№101<\/b>/);
    assert.equal(await prisma.order.count(), 1);
  });

  it("товару немає — пропонуються альтернативи з каталогу; невідомий номер — чесна відповідь", async () => {
    await createProduct(prisma, { name: "Galaxy Explorer", setNumber: "10497", theme: "LEGO Icons", price: "3900", stock: 0 });
    await createProduct(prisma, { name: "Bugatti Bolide", setNumber: "42151", stock: 2 });

    await send(textUpdate(customer, "Чи є LEGO 10497?"));
    let out = joined(customer.id);
    assert.match(out, /На жаль, LEGO Icons 10497 «Galaxy Explorer» зараз немає в наявності/);
    assert.match(out, /42151/, "запропоновано набір, який реально є");
    assert.doesNotMatch(out, /10497 «Galaxy Explorer»<\/b> є в наявності/);

    fake.clear();
    await send(textUpdate(customer, "Шукаю набір LEGO 99999"));
    out = joined(customer.id);
    assert.match(out, /набору LEGO 99999 немає в каталозі/);
  });

  it("пошук за бюджетом і віком", async () => {
    await createProduct(prisma, { name: "Bugatti Bolide", setNumber: "42151", price: "1800", ageMin: 9 });
    await createProduct(prisma, { name: "Express Passenger Train", setNumber: "60337", theme: "LEGO City", price: "2400", ageMin: 7 });
    await createProduct(prisma, { name: "Hogwarts Castle", setNumber: "76419", theme: "LEGO Harry Potter", price: "4200", ageMin: 18 });

    await send(textUpdate(customer, "Покажи набори LEGO до 2000 грн"));
    let out = joined(customer.id);
    assert.match(out, /42151/);
    assert.doesNotMatch(out, /60337|76419/);

    fake.clear();
    await send(textUpdate(customer, "Які набори є для дітей від 8 років?"));
    out = joined(customer.id);
    assert.match(out, /60337/);
    assert.doesNotMatch(out, /42151|76419/);
  });

  it("питання посеред оформлення не ламає оформлення", async () => {
    const p = await createProduct(prisma, { stock: 3 });
    await createProduct(prisma, { name: "Millennium Falcon", setNumber: "75257", theme: "LEGO Star Wars", price: "3500", stock: 1 });
    await send(callbackUpdate(customer, `buy:${p.id}`));
    await send(callbackUpdate(customer, button(customer.id, "ck:q:", "first")));
    fake.clear();
    await send(textUpdate(customer, "а є ще зоряні війни?"));
    const out = joined(customer.id);
    assert.match(out, /75257/);
    assert.match(out, /незавершене оформлення замовлення/);
    const checkout = await prisma.checkout.findFirstOrThrow();
    assert.equal(checkout.fullName, null, "питання не збережено як ім’я");
    assert.equal(checkout.status, "ACTIVE");
  });

  it("не можна замовити більше, ніж доступно", async () => {
    const p = await createProduct(prisma, { stock: 2 });
    await send(callbackUpdate(customer, `buy:${p.id}`));
    fake.clear();
    await send(textUpdate(customer, "5"));
    assert.match(joined(customer.id), /Зараз доступно лише 2 шт\./);
    const checkout = await prisma.checkout.findFirstOrThrow();
    assert.equal(checkout.quantity, null);
  });

  it("зміна даних із підсумку не перепитує інші поля", async () => {
    const p = await createProduct(prisma, { stock: 3 });
    await checkoutToSummary(p.id);
    await send(callbackUpdate(customer, button(customer.id, "ck:edit:")));
    await send(callbackUpdate(customer, button(customer.id, "ck:ef:").replace(/:[A-Z_]+$/, ":CITY")));
    fake.clear();
    await send(textUpdate(customer, "Одеса"));
    const out = joined(customer.id);
    assert.match(out, /Доставка: Одеса, Відділення №5/);
    assert.doesNotMatch(out, /ім’я та прізвище/);
  });

  it("повторне оновлення Telegram (той самий update_id) обробляється лише раз", async () => {
    await createProduct(prisma);
    const update = textUpdate(customer, "Чи є LEGO 42151?");
    await send(update);
    const count = fake.calls.filter((c) => c.method === "sendMessage" || c.method === "sendPhoto").length;
    await send(update);
    assert.equal(fake.calls.filter((c) => c.method === "sendMessage" || c.method === "sendPhoto").length, count);
  });
});

describe("власник магазину", () => {
  it("адмін-команди недоступні покупцям", async () => {
    await send(textUpdate(customer, "/admin"));
    assert.match(joined(customer.id), /доступна лише власнику/);
    await send(callbackUpdate(customer, "a:menu"));
    const answer = fake.calls.filter((c) => c.method === "answerCallbackQuery").pop();
    assert.equal(answer?.payload.text, "⛔ Недоступно");
    await send(textUpdate(owner, "/admin"));
    assert.match(joined(owner.id), /Адмін-панель «Тестовий LEGO»/);
  });

  it("залишки, статуси, ТТН, сповіщення покупцю та пам’ять про покупки", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    await checkoutToSummary(p.id);
    await send(callbackUpdate(customer, button(customer.id, "ck:ok:")));
    assert.deepEqual(await stockOf(p.id), { onHand: 5, reserved: 1 });

    fake.clear();
    await send(textUpdate(owner, "/addstock 42151 3 нова поставка"));
    assert.match(joined(owner.id), /Додано 3 шт\./);
    assert.match(joined(owner.id), /доступно покупцям: <b>7<\/b>/);
    assert.deepEqual(await stockOf(p.id), { onHand: 8, reserved: 1 });

    fake.clear();
    await send(callbackUpdate(owner, "a:os:101:CONFIRMED"));
    assert.match(joined(customer.id), /Ваше замовлення №101 підтверджено магазином!/);

    fake.clear();
    await send(callbackUpdate(owner, "a:os:101:SHIPPED"));
    assert.match(joined(owner.id), /введіть номер ТТН/);
    await send(textUpdate(owner, "20450012345678"));
    assert.match(joined(customer.id), /Замовлення №101 відправлено!/);
    assert.match(joined(customer.id), /20450012345678/);
    assert.deepEqual(await stockOf(p.id), { onHand: 7, reserved: 0 });

    fake.clear();
    await send(callbackUpdate(owner, "a:os:101:DELIVERED"));
    assert.match(joined(customer.id), /Замовлення №101 доставлено/);
    assert.deepEqual(await stockOf(p.id), { onHand: 7, reserved: 0 }, "доставка не списує товар повторно");

    fake.clear();
    await send(callbackUpdate(owner, "a:os:101:CANCELED"));
    const cancelAnswer = fake.calls.filter((c) => c.method === "answerCallbackQuery").pop();
    assert.match(String(cancelAnswer?.payload.text), /Неможливо/);

    fake.clear();
    await send(textUpdate(customer, "/start"));
    assert.match(
      joined(customer.id),
      /Раніше ви замовляли LEGO Technic 42151 «Bugatti Bolide»\. Бажаєте перевірити актуальну наявність цього набору або подивитися схожі моделі\?/,
    );

    fake.clear();
    await send(textUpdate(customer, "Я вже у вас купував"));
    assert.match(joined(customer.id), /Так, бачу ваші замовлення/);

    fake.clear();
    await send(textUpdate(owner, "/customers"));
    assert.match(joined(owner.id), /Олена Коваль/);
    await send(textUpdate(owner, "/stats"));
    assert.match(joined(owner.id), /Статистика магазину/);
  });

  it("скасування адміністратором вимагає підтвердження й повертає резерв", async () => {
    const p = await createProduct(prisma, { stock: 2 });
    await checkoutToSummary(p.id);
    await send(callbackUpdate(customer, button(customer.id, "ck:ok:")));
    fake.clear();
    await send(callbackUpdate(owner, "a:os:101:CANCELED"));
    assert.match(joined(owner.id), /Скасувати замовлення №101\?/);
    assert.deepEqual(await stockOf(p.id), { onHand: 2, reserved: 1 }, "без підтвердження нічого не змінилося");
    await send(callbackUpdate(owner, "a:os!:101:CANCELED"));
    assert.deepEqual(await stockOf(p.id), { onHand: 2, reserved: 0 });
    assert.match(joined(customer.id), /Замовлення №101 скасовано/);
  });

  it("додавання набору через кнопки (/addproduct) з фото", async () => {
    await send(textUpdate(owner, "/addproduct"));
    await send(textUpdate(owner, "Ford Mustang Shelby GT500"));
    await send(textUpdate(owner, "42138"));
    await send(callbackUpdate(owner, button(owner.id, "a:np:theme:").replace(/:\d+$/, ":1")));
    await send(textUpdate(owner, "544"));
    await send(callbackUpdate(owner, "a:np:age:9"));
    await send(callbackUpdate(owner, "a:np:cond:USED"));
    await send(callbackUpdate(owner, "a:np:box:NONE"));
    await send(callbackUpdate(owner, "a:np:comp:COMPLETE"));
    await send(callbackUpdate(owner, "a:np:note:skip"));
    await send(textUpdate(owner, "1500"));
    await send(callbackUpdate(owner, "a:np:stock:2"));
    await send(photoUpdate(owner, "PHOTO_FILE_ID"));
    await send(callbackUpdate(owner, "a:np:desc:skip"));
    assert.match(joined(owner.id), /Перевірте новий набір/);
    await send(callbackUpdate(owner, "a:npok"));
    assert.match(joined(owner.id), /Набір додано до каталогу/);

    const product = await prisma.product.findFirstOrThrow({ where: { setNumber: "42138" } });
    assert.equal(product.theme, "LEGO Technic");
    assert.equal(product.condition, "USED");
    assert.equal(product.boxState, "NONE");
    assert.equal(product.price.toString(), "1500");
    assert.equal(product.stockOnHand, 2);
    assert.equal(product.telegramFileId, "PHOTO_FILE_ID");
    assert.equal(await prisma.stockMovement.count({ where: { productId: product.id, type: "INITIAL" } }), 1);

    fake.clear();
    await send(textUpdate(customer, "Шукаю набір LEGO 42138"));
    const photoCall = fake.calls.find((c) => c.method === "sendPhoto");
    assert.equal(photoCall?.payload.photo, "PHOTO_FILE_ID");
    assert.match(String(photoCall?.payload.caption), /вживаний, ⚠️ без коробки/);
  });

  it("розсилка лише після підтвердження і без відписаних покупців", async () => {
    const other: TestUser = { id: 5552, first_name: "Максим" };
    await send(textUpdate(customer, "/start"));
    await send(textUpdate(other, "/start"));
    await send(textUpdate(other, "/unsubscribe"));
    fake.clear();

    await send(textUpdate(owner, "/broadcast"));
    await send(textUpdate(owner, "Новинки вже в наявності! <скоро>"));
    assert.match(joined(owner.id), /Надіслати це повідомлення <b>2<\/b> покупцям\?/, "власник теж покупець бота, відписаний не рахується");
    assert.equal(fake.messagesTo(customer.id).length, 0, "до підтвердження нічого не надіслано");

    await send(callbackUpdate(owner, "a:bc:ok"));
    for (let i = 0; i < 100; i += 1) {
      const b = await prisma.broadcast.findFirst();
      if (b?.status === "DONE") break;
      await new Promise((r) => setTimeout(r, 50));
    }
    const b = await prisma.broadcast.findFirstOrThrow();
    assert.equal(b.status, "DONE");
    assert.equal(b.sentCount, 2);
    assert.match(joined(customer.id), /Новинки вже в наявності! &lt;скоро&gt;/);
    assert.equal(fake.messagesTo(other.id).length, 0);
    assert.match(joined(owner.id), /Розсилку №1 завершено/);
  });
});
