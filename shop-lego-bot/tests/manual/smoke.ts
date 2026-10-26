// Димовий тест реального процесу: npm run build && npx tsx tests/manual/smoke.ts
// Запускає dist/index.js проти фейкового Telegram Bot API і тестової БД.
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { TEST_DATABASE_URL } from "../helpers/testDb.js";

const calls: Array<{ method: string; body: any }> = [];
let delivered = false;

const server = createServer(async (req, res) => {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  const raw = Buffer.concat(chunks).toString("utf8");
  const method = (req.url ?? "").split("/").pop() ?? "";
  const body = raw ? JSON.parse(raw) : {};
  calls.push({ method, body });
  const reply = (result: unknown) => {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, result }));
  };
  if (method === "getMe") return reply({ id: 42, is_bot: true, first_name: "Smoke", username: "smoke_bot" });
  if (method === "getUpdates") {
    if (!delivered) {
      delivered = true;
      return reply([
        {
          update_id: Date.now(),
          message: {
            message_id: 1,
            date: Math.floor(Date.now() / 1000),
            chat: { id: 5551, type: "private", first_name: "Олена" },
            from: { id: 5551, is_bot: false, first_name: "Олена" },
            text: "/start",
            entities: [{ type: "bot_command", offset: 0, length: 6 }],
          },
        },
      ]);
    }
    setTimeout(() => reply([]), 300);
    return;
  }
  if (method === "sendMessage") return reply({ message_id: 2, date: 0, chat: { id: body.chat_id, type: "private" }, text: body.text });
  return reply(true);
});

async function main() {
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const { port } = server.address() as AddressInfo;
  const logs: string[] = [];
  const appEnv: Record<string, string> = {
    NODE_ENV: "production",
    BOT_TOKEN: "123456789:SMOKEsmokeSMOKEsmokeSMOKEsmoke",
    ADMIN_IDS: "900000001",
    DATABASE_URL: TEST_DATABASE_URL,
    TELEGRAM_API_ROOT: `http://127.0.0.1:${port}`,
    HEALTH_PORT: "18089",
    AI_ENABLED: "false",
    LOG_LEVEL: "info",
  };
  // SMOKE_DOCKER_IMAGE=shop-lego-bot:test — перевірити зібраний Docker-образ замість dist/
  const image = process.env.SMOKE_DOCKER_IMAGE;
  const child = image
    ? spawn(
        "docker",
        [
          "run", "--rm", "--network", "host", "--init",
          ...Object.entries(appEnv).flatMap(([k, v]) => ["-e", `${k}=${v}`]),
          "--entrypoint", "node", image, "dist/index.js",
        ],
        { stdio: ["ignore", "pipe", "pipe"] },
      )
    : spawn(process.execPath, ["dist/index.js"], { env: { ...process.env, ...appEnv }, stdio: ["ignore", "pipe", "pipe"] });
  child.stdout.on("data", (d) => logs.push(String(d)));
  child.stderr.on("data", (d) => logs.push(String(d)));

  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline && !calls.some((c) => c.method === "sendMessage" && c.body.chat_id === 5551)) {
    await new Promise((r) => setTimeout(r, 200));
  }
  const greeting = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === 5551);
  console.log("Відповідь на /start:", greeting ? String(greeting.body.text).split("\n")[0] : "НЕМАЄ");
  const health = await fetch("http://127.0.0.1:18089/health").then((r) => `${r.status} ${r.statusText}`).catch((e) => String(e));
  console.log("Health-check:", health);
  console.log("Методи Bot API:", [...new Set(calls.map((c) => c.method))].join(", "));

  child.kill("SIGTERM");
  const code = await new Promise<number | null>((r) => child.on("exit", r));
  console.log("Код завершення після SIGTERM:", code);
  const joined = logs.join("");
  for (const marker of ["Підключення до PostgreSQL встановлено", "Бот запущено (long polling)", "Бот зупинено коректно"]) {
    console.log(`${joined.includes(marker) ? "✔" : "✘"} ${marker}`);
  }
  server.close();
  if (!greeting || code !== 0) {
    console.log(joined);
    process.exit(1);
  }
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
