import { createServer, type IncomingMessage, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import type { Update } from "telegraf/types";

export interface ApiCall {
  method: string;
  payload: Record<string, unknown>;
}

/**
 * Мінімальний фейковий сервер Telegram Bot API: приймає запити бота,
 * записує їх і повертає правдоподібні відповіді. Реальний Telegram не потрібен.
 */
export class FakeTelegram {
  readonly calls: ApiCall[] = [];
  private server: Server | null = null;
  private messageId = 1000;
  /** Наступні виклики цього методу завершаться помилкою (для перевірки повторних спроб). */
  failNext = new Map<string, { code: number; description: string; count: number }>();

  async start(): Promise<string> {
    this.server = createServer(async (req, res) => {
      const method = (req.url ?? "").split("/").pop() ?? "";
      const payload = await readBody(req);
      this.calls.push({ method, payload });
      const failure = this.failNext.get(method);
      if (failure && failure.count > 0) {
        failure.count -= 1;
        res.writeHead(failure.code, { "content-type": "application/json" });
        res.end(JSON.stringify({ ok: false, error_code: failure.code, description: failure.description }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: true, result: this.result(method, payload) }));
    });
    await new Promise<void>((resolve) => this.server!.listen(0, "127.0.0.1", resolve));
    const { port } = this.server.address() as AddressInfo;
    return `http://127.0.0.1:${port}`;
  }

  async stop(): Promise<void> {
    await new Promise<void>((resolve) => this.server?.close(() => resolve()) ?? resolve());
  }

  private result(method: string, payload: Record<string, unknown>): unknown {
    switch (method) {
      case "getMe":
        return { id: 123456789, is_bot: true, first_name: "Test LEGO Bot", username: "test_lego_bot" };
      case "sendMessage":
      case "sendPhoto":
      case "editMessageText":
        return {
          message_id: (this.messageId += 1),
          date: Math.floor(Date.now() / 1000),
          chat: { id: Number(payload.chat_id ?? 0), type: "private" },
          ...(payload.text ? { text: payload.text } : {}),
          ...(payload.caption ? { caption: payload.caption } : {}),
        };
      default:
        return true;
    }
  }

  /** Тексти повідомлень (і підписів до фото), надісланих або відредагованих у чаті. */
  messagesTo(chatId: number): string[] {
    return this.calls
      .filter((c) => ["sendMessage", "sendPhoto", "editMessageText"].includes(c.method))
      .filter((c) => Number(c.payload.chat_id) === chatId || (c.method === "editMessageText" && c.payload.chat_id === undefined))
      .map((c) => String(c.payload.text ?? c.payload.caption ?? ""));
  }

  lastMessageTo(chatId: number): string {
    const all = this.messagesTo(chatId);
    return all[all.length - 1] ?? "";
  }

  /** callback_data усіх кнопок в останніх N повідомленнях чату. */
  buttonsTo(chatId: number, lastN = 5): string[] {
    const calls = this.calls
      .filter((c) => ["sendMessage", "sendPhoto", "editMessageText"].includes(c.method))
      .filter((c) => Number(c.payload.chat_id) === chatId)
      .slice(-lastN);
    const result: string[] = [];
    for (const c of calls) {
      const markup = c.payload.reply_markup as { inline_keyboard?: Array<Array<{ callback_data?: string }>> } | undefined;
      for (const row of markup?.inline_keyboard ?? []) {
        for (const b of row) if (b.callback_data) result.push(b.callback_data);
      }
    }
    return result;
  }

  clear(): void {
    this.calls.length = 0;
  }
}

async function readBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw) return {};
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return { raw };
  }
}

// ───── Конструктор оновлень Telegram ─────

let nextUpdateId = 1;

export interface TestUser {
  id: number;
  first_name: string;
  username?: string;
}

const now = () => Math.floor(Date.now() / 1000);

export function textUpdate(user: TestUser, text: string): Update {
  const id = nextUpdateId++;
  const command = text.startsWith("/") ? text.split(" ")[0]! : null;
  return {
    update_id: id,
    message: {
      message_id: id,
      date: now(),
      chat: { id: user.id, type: "private", first_name: user.first_name },
      from: { id: user.id, is_bot: false, first_name: user.first_name, ...(user.username ? { username: user.username } : {}) },
      text,
      ...(command ? { entities: [{ type: "bot_command", offset: 0, length: command.length }] } : {}),
    },
  } as Update;
}

export function callbackUpdate(user: TestUser, data: string): Update {
  const id = nextUpdateId++;
  return {
    update_id: id,
    callback_query: {
      id: String(id),
      from: { id: user.id, is_bot: false, first_name: user.first_name },
      chat_instance: "test",
      data,
      message: {
        message_id: 500,
        date: now(),
        chat: { id: user.id, type: "private", first_name: user.first_name },
        text: "попереднє повідомлення",
      },
    },
  } as Update;
}

export function contactUpdate(user: TestUser, phone: string): Update {
  const id = nextUpdateId++;
  return {
    update_id: id,
    message: {
      message_id: id,
      date: now(),
      chat: { id: user.id, type: "private", first_name: user.first_name },
      from: { id: user.id, is_bot: false, first_name: user.first_name },
      contact: { phone_number: phone, first_name: user.first_name, user_id: user.id },
    },
  } as Update;
}

export function photoUpdate(user: TestUser, fileId: string, caption?: string): Update {
  const id = nextUpdateId++;
  return {
    update_id: id,
    message: {
      message_id: id,
      date: now(),
      chat: { id: user.id, type: "private", first_name: user.first_name },
      from: { id: user.id, is_bot: false, first_name: user.first_name },
      photo: [
        { file_id: `${fileId}_small`, file_unique_id: "s", width: 90, height: 90 },
        { file_id: fileId, file_unique_id: "l", width: 800, height: 800 },
      ],
      ...(caption ? { caption } : {}),
    },
  } as Update;
}
