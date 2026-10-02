import "server-only";
import type { Order, OrderItem } from "@prisma/client";
import { absoluteUrl, siteConfig } from "@/config/site";
import { formatUAH } from "@/lib/money";
import { sendMail } from "@/lib/mail";
import { DELIVERY_METHODS, describeDelivery } from "@/lib/delivery/methods";

export async function sendOrderConfirmation(order: Order & { items: OrderItem[] }) {
  const link = absoluteUrl(`/order/${order.number}?t=${order.accessToken}`);
  const lines = order.items.map((i) => `• ${i.productName} (${i.productSku}) × ${i.quantity} — ${formatUAH(i.unitPrice * i.quantity)}`);
  const text = [
    `Дякуємо за замовлення, ${order.contactName}!`,
    ``,
    `Замовлення №${order.number}`,
    ...lines,
    ``,
    `Доставка: ${DELIVERY_METHODS[order.deliveryMethod].label} — ${describeDelivery(order.deliveryMethod, order.deliveryData)} (${order.deliveryCost ? formatUAH(order.deliveryCost) : "безкоштовно"})`,
    `Разом: ${formatUAH(order.total)}`,
    `Оплата: ${order.paymentMethod === "COD" ? "при отриманні" : "онлайн (LiqPay)"}`,
    ``,
    `Статус замовлення: ${link}`,
    ``,
    `— Команда «${siteConfig.name}»`,
  ].join("\n");
  await sendMail({ to: order.contactEmail, subject: `Замовлення №${order.number} прийнято — ${siteConfig.name}`, text });
}
