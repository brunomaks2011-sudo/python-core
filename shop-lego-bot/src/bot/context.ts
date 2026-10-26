import type { Context } from "telegraf";
import type { Customer } from "../generated/prisma/client.js";
import type { Services } from "../services.js";

/** Контекст оновлення Telegram із сервісами магазину та даними покупця. */
export interface BotContext extends Context {
  services: Services;
  /** Покупець (заповнюється middleware для кожного користувача). */
  customer: Customer;
  /** Чи є користувач власником/адміністратором (ADMIN_IDS). */
  isAdmin: boolean;
}
