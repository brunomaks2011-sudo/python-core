import "../helpers/setupEnv.js";
import assert from "node:assert/strict";
import { after, before, beforeEach, describe, it } from "node:test";
import { InvalidTransitionError, ValidationError } from "../../src/lib/errors.js";
import { createServices, type Services } from "../../src/services.js";
import type { PrismaClient } from "../../src/database/client.js";
import {
  ADMIN_ID,
  createProduct,
  fakeSender,
  migrateTestDb,
  resetDb,
  testConfig,
  testPrisma,
} from "../helpers/testDb.js";

let prisma: PrismaClient;
let s: Services;
let sender: ReturnType<typeof fakeSender>;

async function readyCheckout(telegramId: number, productId: number, quantity: number) {
  const customer = await s.customers.upsertFromTelegram({ id: telegramId, first_name: "Тест" });
  const started = await s.checkout.start(customer.id, { productId, quantity });
  const product = await s.products.getByIdOrThrow(productId);
  await s.checkout.update(customer.id, started.nonce, {
    fullName: "Іван Петренко",
    phone: "+380671234567",
    city: "Київ",
    deliveryPoint: "Відділення №1",
    paymentMethod: "CASH_ON_DELIVERY",
    quotedUnitPrice: product.price,
    step: "SUMMARY",
  });
  return { customer, nonce: started.nonce };
}

async function placeOrder(telegramId: number, productId: number, quantity: number) {
  const { customer, nonce } = await readyCheckout(telegramId, productId, quantity);
  const result = await s.orders.placeOrder({ customerId: customer.id, nonce });
  assert.equal(result.kind, "created");
  return { customer, order: (result as Extract<typeof result, { kind: "created" }>).order, nonce };
}

const admin = { actorType: "ADMIN" as const, actorTelegramId: BigInt(ADMIN_ID) };

async function stock(productId: number) {
  const p = await prisma.product.findUniqueOrThrow({ where: { id: productId } });
  return { onHand: p.stockOnHand, reserved: p.stockReserved, available: p.stockOnHand - p.stockReserved };
}

before(async () => {
  migrateTestDb();
  prisma = testPrisma();
  sender = fakeSender();
  s = createServices({ config: testConfig(), prisma, telegram: sender, anthropic: null });
});

after(async () => {
  await prisma.$disconnect();
});

beforeEach(async () => {
  await resetDb(prisma);
  sender.sent.length = 0;
});

describe("оформлення замовлення та резерв", () => {
  it("приклад із ТЗ: 5 → 4 після замовлення, +3 від власника → 7", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { order } = await placeOrder(1001, p.id, 1);
    assert.equal(order.id, 101, "номери замовлень починаються зі 101");
    assert.equal(order.status, "NEW");
    assert.equal(order.totalAmount.toString(), "1800");
    assert.deepEqual(await stock(p.id), { onHand: 5, reserved: 1, available: 4 });

    const levels = await s.inventory.addStock(p.id, 3, BigInt(ADMIN_ID), "Нова поставка");
    assert.deepEqual(levels, { onHand: 8, reserved: 1, available: 7 });

    const movements = await prisma.stockMovement.findMany({ where: { productId: p.id }, orderBy: { id: "asc" } });
    assert.deepEqual(
      movements.map((m) => m.type),
      ["ORDER_RESERVE", "RESTOCK"],
    );
  });

  it("подвійне натискання «Підтвердити» не створює друге замовлення", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { customer, nonce } = await readyCheckout(1001, p.id, 2);
    const [a, b] = await Promise.all([
      s.orders.placeOrder({ customerId: customer.id, nonce }),
      s.orders.placeOrder({ customerId: customer.id, nonce }),
    ]);
    const kinds = [a.kind, b.kind].sort();
    assert.deepEqual(kinds, ["created", "duplicate"]);
    assert.equal(await prisma.order.count(), 1);
    assert.deepEqual(await stock(p.id), { onHand: 5, reserved: 2, available: 3 });
    const again = await s.orders.placeOrder({ customerId: customer.id, nonce });
    assert.equal(again.kind, "duplicate");
  });

  it("одночасні замовлення на останній набір: успішне лише одне", async () => {
    const p = await createProduct(prisma, { stock: 1 });
    const first = await readyCheckout(2001, p.id, 1);
    const second = await readyCheckout(2002, p.id, 1);
    const results = await Promise.all([
      s.orders.placeOrder({ customerId: first.customer.id, nonce: first.nonce }),
      s.orders.placeOrder({ customerId: second.customer.id, nonce: second.nonce }),
    ]);
    const kinds = results.map((r) => r.kind).sort();
    assert.deepEqual(kinds, ["created", "insufficient_stock"]);
    assert.deepEqual(await stock(p.id), { onHand: 1, reserved: 1, available: 0 });
  });

  it("10 покупців одночасно на 3 набори — продано рівно 3", async () => {
    const p = await createProduct(prisma, { stock: 3 });
    const checkouts = [];
    for (let i = 0; i < 10; i += 1) checkouts.push(await readyCheckout(3000 + i, p.id, 1));
    const results = await Promise.all(
      checkouts.map((c) => s.orders.placeOrder({ customerId: c.customer.id, nonce: c.nonce })),
    );
    assert.equal(results.filter((r) => r.kind === "created").length, 3);
    assert.equal(results.filter((r) => r.kind === "insufficient_stock").length, 7);
    assert.deepEqual(await stock(p.id), { onHand: 3, reserved: 3, available: 0 });
    assert.equal(await prisma.order.count(), 3);
  });

  it("не можна замовити більше, ніж є", async () => {
    const p = await createProduct(prisma, { stock: 2 });
    const { customer, nonce } = await readyCheckout(1001, p.id, 3);
    const result = await s.orders.placeOrder({ customerId: customer.id, nonce });
    assert.deepEqual(result, { kind: "insufficient_stock", available: 2 });
    assert.equal(await prisma.order.count(), 0);
    assert.deepEqual(await stock(p.id), { onHand: 2, reserved: 0, available: 2 });
  });

  it("зміна ціни після показу підсумку зупиняє оформлення", async () => {
    const p = await createProduct(prisma, { stock: 2, price: "1800" });
    const { customer, nonce } = await readyCheckout(1001, p.id, 1);
    await s.products.update(p.id, { price: "1900" }, BigInt(ADMIN_ID));
    const result = await s.orders.placeOrder({ customerId: customer.id, nonce });
    assert.equal(result.kind, "price_changed");
    assert.equal(await prisma.order.count(), 0);
    assert.equal((await stock(p.id)).reserved, 0);
    const changes = await prisma.productChange.findMany({ where: { productId: p.id, field: "price" } });
    assert.equal(changes.length, 1);
    assert.equal(changes[0]!.oldValue, "1800.00");
    assert.equal(changes[0]!.newValue, "1900.00");
  });

  it("архівований товар не можна замовити", async () => {
    const p = await createProduct(prisma, { stock: 2 });
    const { customer, nonce } = await readyCheckout(1001, p.id, 1);
    await s.products.setStatus(p.id, "ARCHIVED", BigInt(ADMIN_ID));
    const result = await s.orders.placeOrder({ customerId: customer.id, nonce });
    assert.equal(result.kind, "unavailable");
  });
});

describe("статуси замовлення та склад", () => {
  it("відправлення списує товар один раз; доставка не списує повторно", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { order, customer } = await placeOrder(1001, p.id, 2);
    for (const to of ["CONFIRMED", "PAID", "PACKING"] as const) {
      await s.orders.changeStatus({ orderId: order.id, to, actor: admin });
      assert.deepEqual(await stock(p.id), { onHand: 5, reserved: 2, available: 3 });
    }
    await s.orders.changeStatus({ orderId: order.id, to: "SHIPPED", actor: admin, trackingNumber: "20450000000000" });
    assert.deepEqual(await stock(p.id), { onHand: 3, reserved: 0, available: 3 });
    const repeat = await s.orders.changeStatus({ orderId: order.id, to: "SHIPPED", actor: admin });
    assert.equal(repeat.changed, false);
    await s.orders.changeStatus({ orderId: order.id, to: "DELIVERED", actor: admin });
    assert.deepEqual(await stock(p.id), { onHand: 3, reserved: 0, available: 3 });

    const c = await prisma.customer.findUniqueOrThrow({ where: { id: customer.id } });
    assert.equal(c.totalSpent.toString(), "3600");
    const types = (await prisma.stockMovement.findMany({ where: { productId: p.id }, orderBy: { id: "asc" } })).map((m) => m.type);
    assert.deepEqual(types, ["ORDER_RESERVE", "ORDER_SHIP"]);
    const history = await prisma.orderStatusHistory.findMany({ where: { orderId: order.id }, orderBy: { id: "asc" } });
    assert.deepEqual(
      history.map((h) => h.toStatus),
      ["NEW", "CONFIRMED", "PAID", "PACKING", "SHIPPED", "DELIVERED"],
    );
    const customerNotes = await prisma.notification.findMany({ where: { kind: "ORDER_STATUS_CUSTOMER" } });
    assert.equal(customerNotes.length, 5, "покупець отримує повідомлення про кожну зміну статусу");
    assert.ok(customerNotes.some((n) => n.text.includes("20450000000000")), "ТТН передається покупцю");
  });

  it("скасування повертає зарезервований товар у доступний залишок", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { order } = await placeOrder(1001, p.id, 2);
    await s.orders.changeStatus({ orderId: order.id, to: "CONFIRMED", actor: admin });
    await s.orders.changeStatus({ orderId: order.id, to: "CANCELED", actor: admin, note: "Покупець передумав" });
    assert.deepEqual(await stock(p.id), { onHand: 5, reserved: 0, available: 5 });
    const again = await s.orders.changeStatus({ orderId: order.id, to: "CANCELED", actor: admin });
    assert.equal(again.changed, false);
    assert.deepEqual(await stock(p.id), { onHand: 5, reserved: 0, available: 5 });
    await assert.rejects(
      s.orders.changeStatus({ orderId: order.id, to: "SHIPPED", actor: admin }),
      InvalidTransitionError,
    );
  });

  it("відправлене замовлення не можна скасувати", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { order } = await placeOrder(1001, p.id, 1);
    await s.orders.changeStatus({ orderId: order.id, to: "CONFIRMED", actor: admin });
    await s.orders.changeStatus({ orderId: order.id, to: "SHIPPED", actor: admin });
    await assert.rejects(s.orders.changeStatus({ orderId: order.id, to: "CANCELED", actor: admin }), InvalidTransitionError);
    assert.deepEqual(await stock(p.id), { onHand: 4, reserved: 0, available: 4 });
  });

  it("повернення: склад коригується лише після підтвердження власником", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { order, customer } = await placeOrder(1001, p.id, 1);
    await s.orders.changeStatus({ orderId: order.id, to: "CONFIRMED", actor: admin });
    await s.orders.changeStatus({ orderId: order.id, to: "SHIPPED", actor: admin });
    await s.orders.changeStatus({ orderId: order.id, to: "DELIVERED", actor: admin });
    assert.equal((await prisma.customer.findUniqueOrThrow({ where: { id: customer.id } })).totalSpent.toString(), "1800");

    await s.orders.changeStatus({ orderId: order.id, to: "RETURNED", actor: admin });
    assert.deepEqual(await stock(p.id), { onHand: 4, reserved: 0, available: 4 }, "до підтвердження склад не змінюється");
    assert.equal((await prisma.customer.findUniqueOrThrow({ where: { id: customer.id } })).totalSpent.toString(), "0");

    await s.orders.resolveReturn({ orderId: order.id, restock: true, actorTelegramId: BigInt(ADMIN_ID) });
    assert.deepEqual(await stock(p.id), { onHand: 5, reserved: 0, available: 5 });
    await assert.rejects(
      s.orders.resolveReturn({ orderId: order.id, restock: true, actorTelegramId: BigInt(ADMIN_ID) }),
      InvalidTransitionError,
      "повторне підтвердження повернення не додає товар удруге",
    );
    assert.deepEqual(await stock(p.id), { onHand: 5, reserved: 0, available: 5 });
  });

  it("повернення браку без повернення на склад", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { order } = await placeOrder(1001, p.id, 1);
    await s.orders.changeStatus({ orderId: order.id, to: "CONFIRMED", actor: admin });
    await s.orders.changeStatus({ orderId: order.id, to: "SHIPPED", actor: admin });
    await s.orders.changeStatus({ orderId: order.id, to: "RETURNED", actor: admin });
    const resolved = await s.orders.resolveReturn({ orderId: order.id, restock: false, actorTelegramId: BigInt(ADMIN_ID) });
    assert.equal(resolved.stockState, "WRITTEN_OFF");
    assert.deepEqual(await stock(p.id), { onHand: 4, reserved: 0, available: 4 });
  });

  it("одночасна зміна статусу двома адміністраторами списує товар один раз", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { order } = await placeOrder(1001, p.id, 2);
    await s.orders.changeStatus({ orderId: order.id, to: "CONFIRMED", actor: admin });
    const results = await Promise.all([
      s.orders.changeStatus({ orderId: order.id, to: "SHIPPED", actor: admin }),
      s.orders.changeStatus({ orderId: order.id, to: "SHIPPED", actor: admin }),
    ]);
    assert.deepEqual(results.map((r) => r.changed).sort(), [false, true]);
    assert.deepEqual(await stock(p.id), { onHand: 3, reserved: 0, available: 3 });
  });
});

describe("ручне коригування складу", () => {
  it("не можна списати зарезервований товар", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    await placeOrder(1001, p.id, 1);
    await assert.rejects(s.inventory.adjustStock(p.id, -10, BigInt(ADMIN_ID), "брак"), ValidationError);
    const levels = await s.inventory.adjustStock(p.id, -4, BigInt(ADMIN_ID), "брак");
    assert.deepEqual(levels, { onHand: 1, reserved: 1, available: 0 });
    await assert.rejects(s.inventory.adjustStock(p.id, -1, BigInt(ADMIN_ID), "брак"), ValidationError);
  });

  it("CHECK-обмеження БД забороняють від'ємні залишки навіть у прямому SQL", async () => {
    const p = await createProduct(prisma, { stock: 1 });
    await assert.rejects(prisma.$executeRaw`UPDATE products SET stock_on_hand = -1 WHERE id = ${p.id}`);
    await assert.rejects(prisma.$executeRaw`UPDATE products SET stock_reserved = 5 WHERE id = ${p.id}`);
    assert.deepEqual(await stock(p.id), { onHand: 1, reserved: 0, available: 1 });
  });
});

describe("сповіщення (outbox)", () => {
  it("після сповіщення власника статус стає «очікує підтвердження магазину»", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { order } = await placeOrder(1001, p.id, 1);
    const sentCount = await s.notifications.processDue({ orderId: order.id });
    assert.equal(sentCount, 1);
    assert.equal(sender.sent.length, 1);
    assert.equal(sender.sent[0]!.chatId, String(ADMIN_ID));
    assert.match(sender.sent[0]!.text, /Нове замовлення №101/);
    const updated = await prisma.order.findUniqueOrThrow({ where: { id: order.id } });
    assert.equal(updated.status, "AWAITING_CONFIRMATION");
    assert.equal(await s.notifications.processDue({ orderId: order.id }), 0, "повторно не надсилається");
  });

  it("збій Telegram: сповіщення залишається в черзі для повторної спроби", async () => {
    const failing = {
      async sendMessage() {
        throw new Error("network down");
      },
      async sendPhoto() {
        throw new Error("network down");
      },
    };
    const s2 = createServices({ config: testConfig(), prisma, telegram: failing, anthropic: null });
    const p = await createProduct(prisma, { stock: 5 });
    const customer = await s2.customers.upsertFromTelegram({ id: 4001, first_name: "Тест" });
    const started = await s2.checkout.start(customer.id, { productId: p.id, quantity: 1 });
    await s2.checkout.update(customer.id, started.nonce, {
      fullName: "Іван Петренко",
      phone: "+380671234567",
      city: "Київ",
      deliveryPoint: "Відділення №1",
      paymentMethod: "CASH_ON_DELIVERY",
      quotedUnitPrice: p.price,
    });
    const result = await s2.orders.placeOrder({ customerId: customer.id, nonce: started.nonce });
    assert.equal(result.kind, "created");
    assert.equal(await s2.notifications.processDue({}), 0);
    const n = await prisma.notification.findFirstOrThrow({ where: { kind: "ORDER_CREATED_ADMIN" } });
    assert.equal(n.status, "PENDING");
    assert.equal(n.attempts, 1);
    assert.ok(n.nextAttemptAt.getTime() > Date.now(), "наступна спроба відкладена");
    const order = await prisma.order.findFirstOrThrow();
    assert.equal(order.status, "NEW", "статус відповідає реальності: магазин ще не отримав сповіщення");
  });
});

describe("покупці та персональні дані", () => {
  it("історія покупок і /forgetme", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    const { order, customer } = await placeOrder(1001, p.id, 1);
    const sets = await s.customers.purchasedSets(customer.id);
    assert.equal(sets[0]?.title, "LEGO Technic 42151 «Bugatti Bolide»");

    const blocked = await s.customers.forget(customer.id);
    assert.deepEqual(blocked, { ok: false, activeOrderIds: [order.id] }, "активне замовлення блокує видалення");

    await s.orders.changeStatus({ orderId: order.id, to: "CANCELED", actor: admin });
    const done = await s.customers.forget(customer.id);
    assert.deepEqual(done, { ok: true });
    const c = await prisma.customer.findUniqueOrThrow({ where: { id: customer.id } });
    assert.equal(c.phone, null);
    assert.equal(c.fullName, null);
    const o = await prisma.order.findUniqueOrThrow({ where: { id: order.id } });
    assert.equal(o.phone, "—");
    assert.equal(o.totalAmount.toString(), "1800", "фінансові дані для обліку зберігаються");
  });
});
