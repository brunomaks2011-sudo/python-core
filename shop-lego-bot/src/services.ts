import type Anthropic from "@anthropic-ai/sdk";
import type { AppConfig } from "./config/env.js";
import type { PrismaClient } from "./database/client.js";
import { ShopAssistant } from "./ai/assistant.js";
import { StatsService } from "./admin/statsService.js";
import { BroadcastService, type BroadcastSender } from "./broadcast/broadcastService.js";
import { ProductService } from "./catalog/productService.js";
import { ChatHistoryService } from "./chat/chatHistoryService.js";
import { CustomerService } from "./customers/customerService.js";
import { InventoryService } from "./inventory/inventoryService.js";
import { Semaphore, RateLimiter } from "./lib/concurrency.js";
import { logger } from "./lib/logger.js";
import { NotificationService } from "./notifications/notificationService.js";
import { OrderNotifier } from "./notifications/orderNotifier.js";
import { CheckoutService } from "./orders/checkoutService.js";
import { OrderService } from "./orders/orderService.js";
import { UpdateDedupService } from "./state/updateDedupService.js";
import { UserStateService } from "./state/userStateService.js";

export interface Services {
  config: AppConfig;
  prisma: PrismaClient;
  products: ProductService;
  inventory: InventoryService;
  orders: OrderService;
  checkout: CheckoutService;
  customers: CustomerService;
  notifications: NotificationService;
  broadcasts: BroadcastService;
  userState: UserStateService;
  chat: ChatHistoryService;
  dedup: UpdateDedupService;
  stats: StatsService;
  assistant: ShopAssistant | null;
  aiLimiter: RateLimiter;
  aiSemaphore: Semaphore;
}

export function createServices(params: {
  config: AppConfig;
  prisma: PrismaClient;
  telegram: BroadcastSender;
  /** Клієнт Claude API (у тестах можна передати фейковий або null). */
  anthropic?: Anthropic | null;
}): Services {
  const { config, prisma, telegram } = params;
  const shopTexts = {
    contact: config.shop.contact,
    paymentDetails: config.shop.paymentDetails,
    timezone: config.shop.timezone,
  };
  const products = new ProductService(prisma, { lowStockThreshold: config.shop.defaultLowStockThreshold });
  const inventory = new InventoryService(prisma);
  const notifications = new NotificationService(prisma, telegram);
  const notifier = new OrderNotifier(notifications, config.telegram.adminIds, shopTexts);
  const orders = new OrderService(prisma, inventory, notifier);
  const customers = new CustomerService(prisma);

  notifications.setHooks({
    onSent: async (n) => {
      if (n.kind === "ORDER_CREATED_ADMIN" && n.orderId) await orders.markAwaitingConfirmation(n.orderId);
    },
    onUnreachable: async (chatId) => customers.markBlockedByTelegramId(chatId, true),
  });

  const anthropic =
    params.anthropic === undefined ? (config.ai.enabled ? ShopAssistant.createClient(config) : null) : params.anthropic;
  const assistant = anthropic ? new ShopAssistant(anthropic, { products, orders }, config) : null;
  if (!assistant) logger.info("Claude AI вимкнено — працює резервний розбір повідомлень без ШІ");

  return {
    config,
    prisma,
    products,
    inventory,
    orders,
    checkout: new CheckoutService(prisma),
    customers,
    notifications,
    broadcasts: new BroadcastService(prisma, telegram, config.broadcastRatePerSecond),
    userState: new UserStateService(prisma),
    chat: new ChatHistoryService(prisma),
    dedup: new UpdateDedupService(prisma),
    stats: new StatsService(prisma),
    assistant,
    aiLimiter: new RateLimiter(config.ai.maxRequestsPerMinute, config.ai.maxRequestsPerDay),
    aiSemaphore: new Semaphore(config.ai.maxConcurrency),
  };
}
