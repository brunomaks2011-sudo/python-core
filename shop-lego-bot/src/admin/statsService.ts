import type { OrderStatus } from "../generated/prisma/client.js";
import type { Prisma, PrismaClient } from "../database/client.js";

export interface PeriodStats {
  orders: number;
  revenue: number;
}

export interface ShopStats {
  byStatus: Partial<Record<OrderStatus, number>>;
  today: PeriodStats;
  week: PeriodStats;
  month: PeriodStats;
  deliveredRevenue: number;
  customersTotal: number;
  customersWithOrders: number;
  activeProducts: number;
  unitsOnHand: number;
  unitsReserved: number;
  lowStock: number;
  outOfStock: number;
  topProducts: Array<{ name: string; setNumber: string | null; theme: string; quantity: number; revenue: number }>;
}

export class StatsService {
  constructor(private readonly prisma: PrismaClient) {}

  async summary(timezone: string): Promise<ShopStats> {
    const byStatusRows = await this.prisma.order.groupBy({ by: ["status"], _count: { _all: true } });
    const byStatus: Partial<Record<OrderStatus, number>> = {};
    for (const row of byStatusRows) byStatus[row.status] = row._count._all;

    const period = async (days: number | "today"): Promise<PeriodStats> => {
      const since =
        days === "today"
          ? await this.startOfToday(timezone)
          : new Date(Date.now() - days * 86_400_000);
      const agg = await this.prisma.order.aggregate({
        where: { createdAt: { gte: since }, status: { notIn: ["CANCELED"] } },
        _count: { _all: true },
        _sum: { totalAmount: true },
      });
      return { orders: agg._count._all, revenue: Number(agg._sum.totalAmount ?? 0) };
    };

    const [today, week, month, delivered, customersTotal, customersWithOrders, stock, top] = await Promise.all([
      period("today"),
      period(7),
      period(30),
      this.prisma.order.aggregate({ where: { status: "DELIVERED" }, _sum: { totalAmount: true } }),
      this.prisma.customer.count(),
      this.prisma.customer.count({ where: { orders: { some: {} } } }),
      this.prisma.$queryRaw<
        Array<{ active: number; on_hand: bigint | null; reserved: bigint | null; low: number; out: number }>
      >`
        SELECT COUNT(*)::int AS active,
               SUM(stock_on_hand) AS on_hand,
               SUM(stock_reserved) AS reserved,
               COUNT(*) FILTER (WHERE stock_on_hand - stock_reserved > 0
                                  AND stock_on_hand - stock_reserved <= low_stock_threshold)::int AS low,
               COUNT(*) FILTER (WHERE stock_on_hand - stock_reserved <= 0)::int AS out
        FROM products WHERE status = 'ACTIVE'`,
      this.prisma.$queryRaw<
        Array<{ product_name: string; set_number: string | null; theme: string; qty: bigint; revenue: Prisma.Decimal }>
      >`
        SELECT oi.product_name, oi.set_number, oi.theme, SUM(oi.quantity) AS qty, SUM(oi.line_total) AS revenue
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE o.status <> 'CANCELED' AND o.created_at >= NOW() - INTERVAL '30 days'
        GROUP BY oi.product_id, oi.product_name, oi.set_number, oi.theme
        ORDER BY qty DESC, revenue DESC
        LIMIT 5`,
    ]);
    const s = stock[0];
    return {
      byStatus,
      today,
      week,
      month,
      deliveredRevenue: Number(delivered._sum.totalAmount ?? 0),
      customersTotal,
      customersWithOrders,
      activeProducts: s?.active ?? 0,
      unitsOnHand: Number(s?.on_hand ?? 0),
      unitsReserved: Number(s?.reserved ?? 0),
      lowStock: s?.low ?? 0,
      outOfStock: s?.out ?? 0,
      topProducts: top.map((t) => ({
        name: t.product_name,
        setNumber: t.set_number,
        theme: t.theme,
        quantity: Number(t.qty),
        revenue: Number(t.revenue),
      })),
    };
  }

  /** Початок поточної доби в часовому поясі магазину (як UTC-момент). */
  private async startOfToday(timezone: string): Promise<Date> {
    const rows = await this.prisma.$queryRaw<Array<{ start: Date }>>`
      SELECT (date_trunc('day', NOW() AT TIME ZONE ${timezone}) AT TIME ZONE ${timezone}) AS start`;
    return rows[0]?.start ?? new Date(new Date().setHours(0, 0, 0, 0));
  }
}
