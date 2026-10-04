// Запуск сайту на власному комп'ютері однією командою — без Docker.
//   node scripts/local-start.mjs   (або подвійний клік по start-windows.bat / start-mac.command)
// Що робить:
//   1) створює .env з випадковим секретом (якщо його ще немає);
//   2) запускає вбудований PostgreSQL у папці .local-db (порт 54329);
//   3) застосовує міграції, а при першому запуску заповнює базу тестовими товарами;
//   4) стартує сайт і відкриває браузер. Зупинка — Ctrl+C.
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync, copyFileSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
process.chdir(root);

const DB_PORT = 54329;
const DB_DIR = path.join(root, ".local-db");
const DB_USER = "shop";
const DB_PASSWORD = "shop";
const DB_NAME = "shop";
const DEFAULT_ADMIN_PASSWORD = "Admin12345!";

const log = (msg) => console.log(`\x1b[33m▶\x1b[0m ${msg}`);

// ---------- 1. .env ----------
if (!existsSync(".env")) {
  copyFileSync(".env.example", ".env");
  log("Створено файл .env");
}
let envText = readFileSync(".env", "utf8");
const envValue = (key) => envText.match(new RegExp(`^${key}=["']?([^"'\\n]*)["']?`, "m"))?.[1] ?? "";
const setEnv = (key, value) => {
  envText = new RegExp(`^${key}=`, "m").test(envText)
    ? envText.replace(new RegExp(`^${key}=.*$`, "m"), `${key}="${value}"`)
    : `${envText.trimEnd()}\n${key}="${value}"\n`;
};
if (!envValue("AUTH_SECRET")) setEnv("AUTH_SECRET", randomBytes(32).toString("base64"));
if (!envValue("ADMIN_PASSWORD")) setEnv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD);
if (!envValue("ADMIN_EMAIL")) setEnv("ADMIN_EMAIL", "admin@example.com");
writeFileSync(".env", envText);

// ---------- 2. PostgreSQL ----------
const freePort = (start) =>
  new Promise((resolve) => {
    const srv = net.createServer();
    srv.once("error", () => resolve(freePort(start + 1)));
    srv.once("listening", () => srv.close(() => resolve(start)));
    srv.listen(start, "127.0.0.1");
  });

const { default: EmbeddedPostgres } = await import("embedded-postgres");
const firstRun = !existsSync(path.join(DB_DIR, "PG_VERSION"));
const pg = new EmbeddedPostgres({
  databaseDir: DB_DIR,
  port: DB_PORT,
  user: DB_USER,
  password: DB_PASSWORD,
  persistent: true,
  // Postgres не запускається від root (актуально лише для Linux-серверів)
  createPostgresUser: typeof process.getuid === "function" && process.getuid() === 0,
  onLog: () => {},
});

if (firstRun) log("Перший запуск: створюю базу даних (близько хвилини)…");
if (firstRun) await pg.initialise();
await pg.start();
if (firstRun) await pg.createDatabase(DB_NAME);
log(`PostgreSQL працює на порту ${DB_PORT}`);

const databaseUrl = `postgresql://${DB_USER}:${DB_PASSWORD}@127.0.0.1:${DB_PORT}/${DB_NAME}?schema=public`;
const childEnv = { ...process.env, DATABASE_URL: databaseUrl };

let stopping = false;
const children = new Set();
const isWin = process.platform === "win32";

/** Зупиняє процес разом з усіма дочірніми (npx → next → workers). */
function killTree(child) {
  if (child.exitCode !== null) return Promise.resolve();
  const exited = new Promise((r) => child.once("exit", r));
  try {
    if (isWin) spawn(`taskkill /pid ${child.pid} /T /F`, { shell: true, stdio: "ignore" });
    else process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill();
  }
  return Promise.race([exited, new Promise((r) => setTimeout(r, 5000))]);
}

async function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  log("Зупиняю сайт…");
  await Promise.all([...children].map(killTree));
  log("Зупиняю базу даних…");
  await pg.stop().catch(() => {});
  process.exit(code);
}
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

function run(cmd, extraEnv = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, { shell: true, stdio: "inherit", detached: !isWin, env: { ...childEnv, ...extraEnv } });
    children.add(child);
    child.on("exit", (code) => {
      children.delete(child);
      code === 0 ? resolve() : reject(new Error(`Команда завершилась з помилкою: ${cmd}`));
    });
  });
}

try {
  // ---------- 3. Міграції та тестові дані ----------
  log("Застосовую міграції…");
  await run("npx prisma migrate deploy");
  const seededMarker = `${DB_DIR}.seeded`;
  if (!existsSync(seededMarker)) {
    log("Заповнюю каталог тестовими товарами…");
    await run("npx prisma db seed");
    writeFileSync(seededMarker, new Date().toISOString());
  }

  // ---------- 4. Сайт ----------
  const port = await freePort(3000);
  const url = `http://localhost:${port}`;
  log(`Запускаю сайт на ${url} …`);
  const site = spawn(`npx next dev -p ${port}`, {
    shell: true,
    stdio: "inherit",
    detached: !isWin,
    env: { ...childEnv, NEXT_PUBLIC_SITE_URL: url, AUTH_URL: url },
  });
  children.add(site);
  site.on("exit", () => shutdown(0));

  // Чекаємо, поки сайт відповість, і відкриваємо браузер
  for (let i = 0; i < 120 && !stopping; i++) {
    try {
      const res = await fetch(url);
      if (res.ok) break;
    } catch {}
    await new Promise((r) => setTimeout(r, 1000));
  }
  const opener = process.platform === "win32" ? `start "" "${url}"` : process.platform === "darwin" ? `open "${url}"` : `xdg-open "${url}"`;
  spawn(opener, { shell: true, stdio: "ignore" }).on("error", () => {});

  const admin = envValue("ADMIN_EMAIL") || "admin@example.com";
  console.log(`
\x1b[32m✔ Сайт працює: ${url}\x1b[0m
  Адмін-панель: ${url}/admin
  Вхід:         ${admin} / пароль з файлу .env (ADMIN_PASSWORD${firstRun && envValue("ADMIN_PASSWORD") === DEFAULT_ADMIN_PASSWORD ? `, зараз ${DEFAULT_ADMIN_PASSWORD}` : ""})
  Зупинити:     Ctrl+C у цьому вікні
`);
} catch (e) {
  console.error(`\x1b[31m✖ ${e.message}\x1b[0m`);
  await shutdown(1);
}
