import { Markup } from "telegraf";
import type { OrderStatus } from "../generated/prisma/client.js";
import type { Tx } from "../database/client.js";
import { cb } from "../bot/callbackData.js";
import { productTitle } from "../catalog/productPresenter.js";
import { escapeHtml } from "../lib/format.js";
import { adminOrderCreatedText, customerStatusText, type ShopTexts } from "../orders/orderPresenter.js";
import type { OrderFull } from "../orders/types.js";
import type { NotificationService } from "./notificationService.js";

export interface StockSnapshot {
  productId: number;
  onHand: number;
  reserved: number;
  available: number;
  lowStockThreshold: number;
}

/** Формує сповіщення про замовлення й записує їх у чергу в межах транзакції. */
export class OrderNotifier {
  constructor(
    private readonly notifications: NotificationService,
    private readonly adminIds: bigint[],
    private readonly shop: ShopTexts,
  ) {}

  async orderCreated(tx: Tx, order: OrderFull, stock: StockSnapshot[]): Promise<void> {
    const text = adminOrderCreatedText(order, stock, this.shop.timezone);
    const keyboard = Markup.inlineKeyboard([
      [
        Markup.button.callback("✅ Підтвердити", cb.adminOrderStatus(order.id, "CONFIRMED")),
        Markup.button.callback("❌ Скасувати", cb.adminOrderStatus(order.id, "CANCELED")),
      ],
      [Markup.button.callback("📋 Відкрити замовлення", cb.adminOrder(order.id))],
    ]).reply_markup;
    await this.notifications.enqueue(
      tx,
      this.adminIds.map((adminId) => ({
        kind: "ORDER_CREATED_ADMIN",
        chatId: adminId,
        text,
        replyMarkup: keyboard,
        dedupKey: `order:${order.id}:created:${adminId}`,
        orderId: order.id,
      })),
    );

    for (const s of stock) {
      if (s.available > s.lowStockThreshold) continue;
      const item = order.items.find((i) => i.productId === s.productId);
      if (!item) continue;
      const title = escapeHtml(productTitle({ theme: item.theme, setNumber: item.setNumber, name: item.productName }));
      const lowText =
        s.available === 0
          ? `⚠️ <b>Закінчився товар:</b> ${title}\nДоступно покупцям: 0 (на складі ${s.onHand}, у резерві ${s.reserved}).`
          : `⚠️ <b>Товар закінчується:</b> ${title}\nДоступно покупцям: ${s.available} (на складі ${s.onHand}, у резерві ${s.reserved}).`;
      await this.notifications.enqueue(
        tx,
        this.adminIds.map((adminId) => ({
          kind: "LOW_STOCK_ADMIN",
          chatId: adminId,
          text: `${lowText}\nПоповнити: /addstock`,
          replyMarkup: Markup.inlineKeyboard([
            [Markup.button.callback("➕ Додати на склад", cb.adminProductStock(s.productId, "add"))],
          ]).reply_markup,
          dedupKey: `lowstock:${s.productId}:${order.id}:${adminId}`,
          orderId: order.id,
        })),
      );
    }
  }

  async statusChanged(tx: Tx, order: OrderFull, to: OrderStatus, historyId: number, note?: string | null) {
    const text = customerStatusText(order, to, this.shop, note);
    if (!text) return;
    await this.notifications.enqueue(tx, {
      kind: "ORDER_STATUS_CUSTOMER",
      chatId: order.customer.telegramId,
      text,
      replyMarkup: Markup.inlineKeyboard([[Markup.button.callback("📦 Мої замовлення", cb.myOrders())]]).reply_markup,
      dedupKey: `order:${order.id}:status:${historyId}`,
      orderId: order.id,
    });
  }

  async returnResolved(tx: Tx, order: OrderFull): Promise<void> {
    await this.notifications.enqueue(tx, {
      kind: "ORDER_RETURN_CUSTOMER",
      chatId: order.customer.telegramId,
      text: `↩️ Магазин отримав повернений товар за замовленням №${order.id}. Дякуємо! Якщо маєте запитання щодо повернення коштів — напишіть нам.`,
      dedupKey: `order:${order.id}:return-resolved`,
      orderId: order.id,
    });
  }
}
