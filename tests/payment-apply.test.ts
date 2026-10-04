import { beforeEach, describe, expect, it, vi } from "vitest";

const order = {
  id: "o1",
  number: "261002-12345",
  total: 155900,
  status: "NEW",
  paymentStatus: "PENDING",
};
const db = {
  findUnique: vi.fn(),
  update: vi.fn(),
};
vi.mock("@/lib/prisma", () => ({ prisma: { order: db } }));
vi.mock("@/auth", () => ({ auth: vi.fn() }));

const { applyPaymentResult } = await import("@/lib/orders/payment");

const cb = (o: Partial<Parameters<typeof applyPaymentResult>[0]> = {}) => ({
  externalId: "261002-12345-abc",
  status: "paid" as const,
  amount: 155900,
  currency: "UAH",
  providerStatus: "success",
  ...o,
});

describe("застосування результату оплати", () => {
  beforeEach(() => {
    db.findUnique.mockReset().mockResolvedValue({ ...order });
    db.update.mockReset().mockResolvedValue({});
  });

  it("позначає замовлення оплаченим", async () => {
    expect(await applyPaymentResult(cb())).toBe("updated");
    expect(db.update).toHaveBeenCalledWith({
      where: { id: "o1" },
      data: expect.objectContaining({ paymentStatus: "PAID", status: "PAID", paidAt: expect.any(Date) }),
    });
  });

  it("не приймає оплату з іншою сумою або валютою", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(await applyPaymentResult(cb({ amount: 100 }))).toBe("amount_mismatch");
    expect(await applyPaymentResult(cb({ currency: "USD" }))).toBe("amount_mismatch");
    expect(db.update).not.toHaveBeenCalled();
  });

  it("повторний callback не змінює оплачене замовлення", async () => {
    db.findUnique.mockResolvedValue({ ...order, paymentStatus: "PAID", status: "SHIPPED" });
    expect(await applyPaymentResult(cb())).toBe("ignored");
    expect(await applyPaymentResult(cb({ status: "failed" }))).toBe("ignored");
    expect(db.update).not.toHaveBeenCalled();
  });

  it("не змінює статус відправленого замовлення при оплаті", async () => {
    db.findUnique.mockResolvedValue({ ...order, status: "SHIPPED" });
    await applyPaymentResult(cb());
    expect(db.update.mock.calls[0][0].data.status).toBe("SHIPPED");
  });

  it("невдала оплата → FAILED", async () => {
    expect(await applyPaymentResult(cb({ status: "failed" }))).toBe("updated");
    expect(db.update.mock.calls[0][0].data).toEqual({ paymentStatus: "FAILED" });
  });

  it("невідомий платіж", async () => {
    db.findUnique.mockResolvedValue(null);
    expect(await applyPaymentResult(cb())).toBe("not_found");
  });
});
