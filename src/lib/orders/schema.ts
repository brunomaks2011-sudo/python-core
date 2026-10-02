import { z } from "zod";
import { emailSchema, nameSchema, phoneSchema } from "@/lib/validation";

const npRef = z.string().regex(/^[0-9a-f-]{36}$/i, "Некоректний ідентифікатор");
const city = z.string().trim().min(2, "Вкажіть місто").max(100);

export const deliverySchema = z.discriminatedUnion("method", [
  z.object({
    method: z.literal("NP_WAREHOUSE"),
    city,
    cityRef: npRef.optional(),
    warehouse: z.string().trim().min(1, "Оберіть відділення").max(250),
    warehouseRef: npRef.optional(),
  }),
  z.object({
    method: z.literal("NP_POSTOMAT"),
    city,
    cityRef: npRef.optional(),
    warehouse: z.string().trim().min(1, "Оберіть поштомат").max(250),
    warehouseRef: npRef.optional(),
  }),
  z.object({
    method: z.literal("NP_COURIER"),
    city,
    cityRef: npRef.optional(),
    street: z.string().trim().min(2, "Вкажіть вулицю").max(150),
    building: z.string().trim().min(1, "Вкажіть номер будинку").max(20),
    apartment: z.string().trim().max(20).optional(),
  }),
  z.object({
    method: z.literal("UKRPOSHTA"),
    city,
    postalCode: z.string().trim().regex(/^\d{5}$/, "Індекс — 5 цифр"),
    street: z.string().trim().max(150).optional(),
    building: z.string().trim().max(20).optional(),
  }),
  z.object({ method: z.literal("PICKUP") }),
]);
export type DeliveryInput = z.infer<typeof deliverySchema>;

export const checkoutSchema = z.object({
  contact: z.object({ name: nameSchema, phone: phoneSchema, email: emailSchema }),
  delivery: deliverySchema,
  paymentMethod: z.enum(["LIQPAY", "COD"], { error: "Оберіть спосіб оплати" }),
  comment: z.string().trim().max(1000).optional(),
  saveAddress: z.boolean().optional(),
});
export type CheckoutInput = z.infer<typeof checkoutSchema>;
