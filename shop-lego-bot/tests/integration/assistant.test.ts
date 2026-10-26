import "../helpers/setupEnv.js";
import assert from "node:assert/strict";
import { after, before, beforeEach, describe, it } from "node:test";
import Anthropic from "@anthropic-ai/sdk";
import { Telegram } from "telegraf";
import type { UserFromGetMe } from "telegraf/types";
import { SAFE_LEAD_IN } from "../../src/ai/prompt.js";
import { createBot } from "../../src/bot/bot.js";
import type { PrismaClient } from "../../src/database/client.js";
import { createServices, type Services } from "../../src/services.js";
import { FakeTelegram, textUpdate, type TestUser } from "../helpers/fakeTelegram.js";
import { createProduct, migrateTestDb, resetDb, testConfig, testPrisma } from "../helpers/testDb.js";

/**
 * Перевірка інтеграції з Claude API без реальних запитів: фейковий fetch повертає
 * заздалегідь записані відповіді Messages API й зберігає тіла запитів для перевірки.
 */
type ScriptedTurn =
  | { toolUse: { name: string; input: Record<string, unknown> } }
  | { text: string }
  | { refusal: true }
  | { httpError: number };

class MockClaude {
  readonly requests: Array<{ headers: Record<string, string>; body: Record<string, any> }> = [];
  script: ScriptedTurn[] = [];
  private counter = 0;

  readonly fetch = async (_url: unknown, init?: RequestInit): Promise<Response> => {
    const headers = Object.fromEntries(new Headers(init?.headers).entries());
    const body = JSON.parse(String(init?.body ?? "{}"));
    this.requests.push({ headers, body });
    const turn = this.script.shift();
    if (!turn) throw new Error("Сценарій відповідей Claude вичерпано");
    if ("httpError" in turn) {
      return new Response(JSON.stringify({ type: "error", error: { type: "api_error", message: "boom" } }), {
        status: turn.httpError,
        headers: { "content-type": "application/json" },
      });
    }
    this.counter += 1;
    const base = {
      id: `msg_${this.counter}`,
      type: "message",
      role: "assistant",
      model: body.model,
      stop_sequence: null,
      stop_details: null,
      usage: { input_tokens: 100, output_tokens: 20, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 },
    };
    const message =
      "toolUse" in turn
        ? {
            ...base,
            content: [
              { type: "thinking", thinking: "", signature: "sig" },
              { type: "tool_use", id: `toolu_${this.counter}`, name: turn.toolUse.name, input: turn.toolUse.input },
            ],
            stop_reason: "tool_use",
          }
        : "refusal" in turn
          ? { ...base, content: [], stop_reason: "refusal", stop_details: { type: "refusal", category: null, explanation: null } }
          : { ...base, content: [{ type: "text", text: turn.text }], stop_reason: "end_turn" };
    return new Response(JSON.stringify(message), {
      status: 200,
      headers: { "content-type": "application/json", "request-id": `req_${this.counter}` },
    });
  };
}

let prisma: PrismaClient;
let mock: MockClaude;
let services: Services;
let fake: FakeTelegram;
let apiRoot: string;
const customer: TestUser = { id: 7771, first_name: "Андрій" };

const searchInput = (overrides: Record<string, unknown> = {}) => ({
  query: null,
  theme: "LEGO Technic",
  set_number: null,
  min_price: null,
  max_price: null,
  child_age: null,
  condition: null,
  include_out_of_stock: false,
  sort: "relevance",
  limit: 5,
  ...overrides,
});

before(async () => {
  migrateTestDb();
  prisma = testPrisma();
  mock = new MockClaude();
  fake = new FakeTelegram();
  apiRoot = await fake.start();
  const config = testConfig({ AI_ENABLED: "true", ANTHROPIC_API_KEY: "sk-ant-test" });
  const anthropic = new Anthropic({ apiKey: "sk-ant-test", fetch: mock.fetch, maxRetries: 0, baseURL: "http://claude.mock" });
  services = createServices({ config, prisma, telegram: new Telegram(config.telegram.token, { apiRoot }), anthropic });
});

after(async () => {
  await fake.stop();
  await prisma.$disconnect();
});

beforeEach(async () => {
  await resetDb(prisma);
  mock.requests.length = 0;
  mock.script = [];
  fake.clear();
});

async function ask(text: string) {
  const c = await services.customers.upsertFromTelegram({ id: customer.id, first_name: customer.first_name });
  return services.assistant!.respond({ customer: c, text, history: [], lastShown: [], purchased: [], activeCheckoutTitle: null });
}

describe("Claude: виклик інструментів і перевірка відповіді", () => {
  it("пошук → показ карток → короткий текст; параметри запиту коректні", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    mock.script = [
      { toolUse: { name: "search_products", input: searchInput() } },
      { toolUse: { name: "show_products", input: { product_ids: [p.id] } } },
      { text: "Так, у нас є набори LEGO Technic! Ось варіанти:" },
    ];
    const reply = await ask("Є технік?");
    assert.ok(reply);
    assert.equal(reply.text, "Так, у нас є набори LEGO Technic! Ось варіанти:");
    assert.deepEqual(reply.showProductIds, [p.id]);
    assert.equal(reply.guardTriggered, false);

    assert.equal(mock.requests.length, 3);
    const first = mock.requests[0]!;
    assert.equal(first.body.model, "claude-opus-5-5");
    assert.deepEqual(first.body.output_config, { effort: "low" });
    assert.equal(first.body.fallbacks, "default");
    assert.match(first.headers["anthropic-beta"] ?? "", /server-side-fallback-2026-07-01/);
    assert.equal(first.body.system[0].cache_control.type, "ephemeral");
    assert.equal(first.body.thinking, undefined, "мислення не вимикається (Opus 5.5)");
    assert.equal(first.body.tool_choice, undefined, "без примусового tool_choice");
    assert.equal(first.body.thread, undefined, "без серверного стану розмови");
    assert.equal(first.body.previous_message_id, undefined);
    assert.equal(first.body.tools.length, 7);
    assert.ok(first.body.tools.every((t: { strict?: boolean }) => t.strict === true));
    const toolsJson = JSON.stringify(first.body.tools);
    assert.doesNotMatch(toolsJson, /"minimum"|"maximum"|"\$schema"/, "непідтримувані strict-режимом ключі видалено");
    assert.match(first.body.messages[0].content, /<customer_message>\nЄ технік\?\n<\/customer_message>/);

    const second = mock.requests[1]!;
    const toolResult = second.body.messages[2].content[0];
    assert.equal(toolResult.type, "tool_result");
    assert.match(String(toolResult.content), /"price_uah":1800/);
    assert.match(String(toolResult.content), /"available_qty":5/);
    assert.equal(second.body.messages[1].content[0].type, "thinking", "блоки мислення повертаються без змін");
  });

  it("вигадана ціна в тексті моделі замінюється, картки — з БД", async () => {
    const p = await createProduct(prisma, { stock: 5, price: "1800" });
    mock.script = [
      { toolUse: { name: "search_products", input: searchInput() } },
      { toolUse: { name: "show_products", input: { product_ids: [p.id] } } },
      { text: "Є Bugatti всього за 1500 грн, а ще 42115 Lamborghini!" },
    ];
    const reply = await ask("що є з техніку?");
    assert.ok(reply);
    assert.equal(reply.guardTriggered, true);
    assert.equal(reply.text, SAFE_LEAD_IN);
    assert.deepEqual(reply.showProductIds, [p.id]);
  });

  it("refusal → null (бот перейде на резервний розбір)", async () => {
    mock.script = [{ refusal: true }];
    assert.equal(await ask("щось"), null);
  });

  it("start_checkout не дозволяє замовити більше, ніж є", async () => {
    const p = await createProduct(prisma, { stock: 1 });
    mock.script = [
      { toolUse: { name: "start_checkout", input: { product_id: p.id, quantity: 2 } } },
      { text: "На жаль, доступний лише 1 набір. Оформити один?" },
    ];
    const reply = await ask("хочу два");
    assert.ok(reply);
    assert.equal(reply.startCheckout, null);
    const toolResult = mock.requests[1]!.body.messages[2].content[0];
    assert.match(String(toolResult.content), /Доступно лише 1 шт/);
  });

  it("невалідні аргументи інструмента повертаються моделі як помилка", async () => {
    await createProduct(prisma, { stock: 1 });
    mock.script = [
      { toolUse: { name: "search_products", input: searchInput({ limit: 500 }) } },
      { text: "Уточніть, будь ласка, що шукаєте." },
    ];
    const reply = await ask("покажи все");
    assert.ok(reply);
    const toolResult = mock.requests[1]!.body.messages[2].content[0];
    assert.equal(toolResult.is_error, true);
  });

  it("get_my_orders повертає лише замовлення поточного покупця", async () => {
    mock.script = [
      { toolUse: { name: "get_my_orders", input: {} } },
      { text: "У вас поки немає замовлень." },
    ];
    await ask("я вже у вас купував");
    const toolResult = mock.requests[1]!.body.messages[2].content[0];
    assert.equal(String(toolResult.content), JSON.stringify({ orders: [] }));
  });
});

describe("Claude у боті", () => {
  function botWithClaude() {
    const { bot } = createBot(services, { detach: false, apiRoot });
    bot.botInfo = { id: 1, is_bot: true, first_name: "B", username: "b" } as UserFromGetMe;
    return bot;
  }

  it("відповідь моделі + картка товару з цінами з БД", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    mock.script = [
      { toolUse: { name: "get_product_details", input: { product_id: p.id } } },
      { toolUse: { name: "show_products", input: { product_ids: [p.id] } } },
      { text: "Так, цей набір є в наявності 👍" },
    ];
    await botWithClaude().handleUpdate(textUpdate(customer, "Скільки коштує бугатті?"));
    const out = fake.messagesTo(customer.id).join("\n");
    assert.match(out, /Так, цей набір є в наявності 👍/);
    assert.match(out, /Ціна: <b>1 800 грн<\/b>/);
    assert.match(out, /В наявності: 5 шт\./);
  });

  it("помилка Claude API → бот відповідає резервним розбором", async () => {
    await createProduct(prisma, { stock: 5 });
    mock.script = [{ httpError: 500 }];
    await botWithClaude().handleUpdate(textUpdate(customer, "Є LEGO Technic?"));
    const out = fake.messagesTo(customer.id).join("\n");
    assert.match(out, /Так, у нас є набір LEGO Technic/);
    assert.match(out, /1 800 грн/);
  });

  it("ШІ запускає оформлення, але далі працює програмна логіка", async () => {
    const p = await createProduct(prisma, { stock: 5 });
    mock.script = [
      { toolUse: { name: "start_checkout", input: { product_id: p.id, quantity: 2 } } },
      { text: "Чудовий вибір! Оформлюємо два набори." },
    ];
    await botWithClaude().handleUpdate(textUpdate(customer, "беру два бугатті"));
    const out = fake.messagesTo(customer.id).join("\n");
    assert.match(out, /Оформлюємо два набори/);
    assert.match(out, /ім’я та прізвище/);
    const checkout = await prisma.checkout.findFirstOrThrow();
    assert.equal(checkout.productId, p.id);
    assert.equal(checkout.quantity, 2);
    assert.equal(await prisma.order.count(), 0, "замовлення не створюється без підтвердження покупцем");
  });
});
