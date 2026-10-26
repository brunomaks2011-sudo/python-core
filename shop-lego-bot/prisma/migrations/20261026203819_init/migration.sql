-- CreateEnum
CREATE TYPE "ProductStatus" AS ENUM ('ACTIVE', 'ARCHIVED');

-- CreateEnum
CREATE TYPE "ProductCondition" AS ENUM ('NEW', 'USED');

-- CreateEnum
CREATE TYPE "BoxState" AS ENUM ('ORIGINAL', 'DAMAGED', 'NONE');

-- CreateEnum
CREATE TYPE "Completeness" AS ENUM ('COMPLETE', 'INCOMPLETE', 'UNCHECKED');

-- CreateEnum
CREATE TYPE "ActorType" AS ENUM ('SYSTEM', 'ADMIN', 'CUSTOMER');

-- CreateEnum
CREATE TYPE "StockMovementType" AS ENUM ('INITIAL', 'RESTOCK', 'ADJUSTMENT', 'ORDER_RESERVE', 'ORDER_RELEASE', 'ORDER_SHIP', 'RETURN_RESTOCK');

-- CreateEnum
CREATE TYPE "OrderStatus" AS ENUM ('NEW', 'AWAITING_CONFIRMATION', 'CONFIRMED', 'PAID', 'PACKING', 'SHIPPED', 'DELIVERED', 'CANCELED', 'RETURNED');

-- CreateEnum
CREATE TYPE "StockState" AS ENUM ('RESERVED', 'RELEASED', 'SHIPPED', 'RESTOCKED', 'WRITTEN_OFF');

-- CreateEnum
CREATE TYPE "PaymentMethod" AS ENUM ('CASH_ON_DELIVERY', 'CARD_TRANSFER', 'BANK_TRANSFER');

-- CreateEnum
CREATE TYPE "CheckoutStatus" AS ENUM ('ACTIVE', 'SUBMITTED', 'CANCELED', 'EXPIRED');

-- CreateEnum
CREATE TYPE "CheckoutStep" AS ENUM ('PRODUCT', 'QUANTITY', 'REUSE_PROFILE', 'FULL_NAME', 'PHONE', 'CITY', 'DELIVERY_POINT', 'PAYMENT', 'SUMMARY', 'EDIT_MENU');

-- CreateEnum
CREATE TYPE "ChatRole" AS ENUM ('USER', 'ASSISTANT');

-- CreateEnum
CREATE TYPE "NotificationStatus" AS ENUM ('PENDING', 'SENT', 'FAILED');

-- CreateEnum
CREATE TYPE "BroadcastStatus" AS ENUM ('DRAFT', 'SENDING', 'DONE', 'CANCELED');

-- CreateTable
CREATE TABLE "products" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "set_number" TEXT,
    "theme" TEXT NOT NULL,
    "pieces" INTEGER,
    "age_min" INTEGER,
    "price" DECIMAL(12,2) NOT NULL,
    "stock_on_hand" INTEGER NOT NULL DEFAULT 0,
    "stock_reserved" INTEGER NOT NULL DEFAULT 0,
    "low_stock_threshold" INTEGER NOT NULL DEFAULT 2,
    "image_url" TEXT,
    "telegram_file_id" TEXT,
    "description" TEXT,
    "condition" "ProductCondition" NOT NULL DEFAULT 'NEW',
    "box_state" "BoxState" NOT NULL DEFAULT 'ORIGINAL',
    "completeness" "Completeness" NOT NULL DEFAULT 'COMPLETE',
    "condition_note" TEXT,
    "status" "ProductStatus" NOT NULL DEFAULT 'ACTIVE',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "archived_at" TIMESTAMP(3),

    CONSTRAINT "products_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "stock_movements" (
    "id" SERIAL NOT NULL,
    "product_id" INTEGER NOT NULL,
    "type" "StockMovementType" NOT NULL,
    "on_hand_delta" INTEGER NOT NULL,
    "reserved_delta" INTEGER NOT NULL,
    "on_hand_after" INTEGER NOT NULL,
    "reserved_after" INTEGER NOT NULL,
    "order_id" INTEGER,
    "actor_type" "ActorType" NOT NULL,
    "actor_telegram_id" BIGINT,
    "note" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "stock_movements_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "product_changes" (
    "id" SERIAL NOT NULL,
    "product_id" INTEGER NOT NULL,
    "field" TEXT NOT NULL,
    "old_value" TEXT,
    "new_value" TEXT,
    "actor_telegram_id" BIGINT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "product_changes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "customers" (
    "id" SERIAL NOT NULL,
    "telegram_id" BIGINT NOT NULL,
    "username" TEXT,
    "first_name" TEXT,
    "last_name" TEXT,
    "language_code" TEXT,
    "full_name" TEXT,
    "phone" TEXT,
    "city" TEXT,
    "delivery_point" TEXT,
    "marketing_opt_out" BOOLEAN NOT NULL DEFAULT false,
    "is_blocked" BOOLEAN NOT NULL DEFAULT false,
    "total_spent" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "last_order_at" TIMESTAMP(3),
    "last_seen_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "anonymized_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "customers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "orders" (
    "id" SERIAL NOT NULL,
    "customer_id" INTEGER NOT NULL,
    "status" "OrderStatus" NOT NULL DEFAULT 'NEW',
    "stock_state" "StockState" NOT NULL DEFAULT 'RESERVED',
    "total_amount" DECIMAL(12,2) NOT NULL,
    "full_name" TEXT NOT NULL,
    "phone" TEXT NOT NULL,
    "city" TEXT NOT NULL,
    "delivery_point" TEXT NOT NULL,
    "payment_method" "PaymentMethod" NOT NULL,
    "tracking_number" TEXT,
    "admin_note" TEXT,
    "checkout_key" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "confirmed_at" TIMESTAMP(3),
    "paid_at" TIMESTAMP(3),
    "shipped_at" TIMESTAMP(3),
    "delivered_at" TIMESTAMP(3),
    "canceled_at" TIMESTAMP(3),
    "returned_at" TIMESTAMP(3),
    "return_resolved_at" TIMESTAMP(3),

    CONSTRAINT "orders_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "order_items" (
    "id" SERIAL NOT NULL,
    "order_id" INTEGER NOT NULL,
    "product_id" INTEGER NOT NULL,
    "product_name" TEXT NOT NULL,
    "set_number" TEXT,
    "theme" TEXT NOT NULL,
    "condition" "ProductCondition" NOT NULL,
    "unit_price" DECIMAL(12,2) NOT NULL,
    "quantity" INTEGER NOT NULL,
    "line_total" DECIMAL(12,2) NOT NULL,

    CONSTRAINT "order_items_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "order_status_history" (
    "id" SERIAL NOT NULL,
    "order_id" INTEGER NOT NULL,
    "from_status" "OrderStatus",
    "to_status" "OrderStatus" NOT NULL,
    "actor_type" "ActorType" NOT NULL,
    "actor_telegram_id" BIGINT,
    "note" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "order_status_history_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "checkouts" (
    "id" SERIAL NOT NULL,
    "customer_id" INTEGER NOT NULL,
    "nonce" INTEGER NOT NULL DEFAULT 1,
    "status" "CheckoutStatus" NOT NULL DEFAULT 'ACTIVE',
    "step" "CheckoutStep" NOT NULL DEFAULT 'PRODUCT',
    "editing_field" "CheckoutStep",
    "product_id" INTEGER,
    "quantity" INTEGER,
    "full_name" TEXT,
    "phone" TEXT,
    "city" TEXT,
    "delivery_point" TEXT,
    "payment_method" "PaymentMethod",
    "quoted_unit_price" DECIMAL(12,2),
    "profile_offered" BOOLEAN NOT NULL DEFAULT false,
    "order_id" INTEGER,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "checkouts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user_states" (
    "telegram_id" BIGINT NOT NULL,
    "scene" TEXT,
    "data" JSONB NOT NULL DEFAULT '{}',
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "user_states_pkey" PRIMARY KEY ("telegram_id")
);

-- CreateTable
CREATE TABLE "processed_updates" (
    "bot_id" BIGINT NOT NULL,
    "update_id" BIGINT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "processed_updates_pkey" PRIMARY KEY ("bot_id","update_id")
);

-- CreateTable
CREATE TABLE "chat_messages" (
    "id" SERIAL NOT NULL,
    "customer_id" INTEGER NOT NULL,
    "role" "ChatRole" NOT NULL,
    "text" TEXT NOT NULL,
    "product_ids" INTEGER[] DEFAULT ARRAY[]::INTEGER[],
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "chat_messages_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "notifications" (
    "id" SERIAL NOT NULL,
    "kind" TEXT NOT NULL,
    "chat_id" BIGINT NOT NULL,
    "text" TEXT NOT NULL,
    "reply_markup" JSONB,
    "dedup_key" TEXT,
    "order_id" INTEGER,
    "status" "NotificationStatus" NOT NULL DEFAULT 'PENDING',
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "next_attempt_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_error" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "sent_at" TIMESTAMP(3),

    CONSTRAINT "notifications_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "broadcasts" (
    "id" SERIAL NOT NULL,
    "admin_telegram_id" BIGINT NOT NULL,
    "text" TEXT NOT NULL,
    "photo_file_id" TEXT,
    "status" "BroadcastStatus" NOT NULL DEFAULT 'DRAFT',
    "total_recipients" INTEGER NOT NULL DEFAULT 0,
    "sent_count" INTEGER NOT NULL DEFAULT 0,
    "failed_count" INTEGER NOT NULL DEFAULT 0,
    "cursor_customer_id" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "started_at" TIMESTAMP(3),
    "finished_at" TIMESTAMP(3),

    CONSTRAINT "broadcasts_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "products_status_theme_idx" ON "products"("status", "theme");

-- CreateIndex
CREATE INDEX "products_set_number_idx" ON "products"("set_number");

-- CreateIndex
CREATE INDEX "stock_movements_product_id_created_at_idx" ON "stock_movements"("product_id", "created_at");

-- CreateIndex
CREATE INDEX "stock_movements_order_id_idx" ON "stock_movements"("order_id");

-- CreateIndex
CREATE INDEX "product_changes_product_id_created_at_idx" ON "product_changes"("product_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "customers_telegram_id_key" ON "customers"("telegram_id");

-- CreateIndex
CREATE INDEX "customers_last_order_at_idx" ON "customers"("last_order_at");

-- CreateIndex
CREATE UNIQUE INDEX "orders_checkout_key_key" ON "orders"("checkout_key");

-- CreateIndex
CREATE INDEX "orders_customer_id_created_at_idx" ON "orders"("customer_id", "created_at");

-- CreateIndex
CREATE INDEX "orders_status_created_at_idx" ON "orders"("status", "created_at");

-- CreateIndex
CREATE INDEX "order_items_order_id_idx" ON "order_items"("order_id");

-- CreateIndex
CREATE INDEX "order_items_product_id_idx" ON "order_items"("product_id");

-- CreateIndex
CREATE INDEX "order_status_history_order_id_created_at_idx" ON "order_status_history"("order_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "checkouts_customer_id_key" ON "checkouts"("customer_id");

-- CreateIndex
CREATE INDEX "checkouts_status_updated_at_idx" ON "checkouts"("status", "updated_at");

-- CreateIndex
CREATE INDEX "processed_updates_created_at_idx" ON "processed_updates"("created_at");

-- CreateIndex
CREATE INDEX "chat_messages_customer_id_created_at_idx" ON "chat_messages"("customer_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "notifications_dedup_key_key" ON "notifications"("dedup_key");

-- CreateIndex
CREATE INDEX "notifications_status_next_attempt_at_idx" ON "notifications"("status", "next_attempt_at");

-- CreateIndex
CREATE INDEX "broadcasts_status_idx" ON "broadcasts"("status");

-- AddForeignKey
ALTER TABLE "stock_movements" ADD CONSTRAINT "stock_movements_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "products"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "stock_movements" ADD CONSTRAINT "stock_movements_order_id_fkey" FOREIGN KEY ("order_id") REFERENCES "orders"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "product_changes" ADD CONSTRAINT "product_changes_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "products"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "orders" ADD CONSTRAINT "orders_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "order_items" ADD CONSTRAINT "order_items_order_id_fkey" FOREIGN KEY ("order_id") REFERENCES "orders"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "order_items" ADD CONSTRAINT "order_items_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "products"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "order_status_history" ADD CONSTRAINT "order_status_history_order_id_fkey" FOREIGN KEY ("order_id") REFERENCES "orders"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "checkouts" ADD CONSTRAINT "checkouts_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "chat_messages" ADD CONSTRAINT "chat_messages_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "customers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- ─────────────────────────────────────────────────────────────────────
-- Додано вручну: обмеження цілісності, яких Prisma не описує у схемі.
-- Вони гарантують на рівні PostgreSQL, що залишки ніколи не стануть
-- від'ємними, а резерв не перевищить фізичну кількість на складі —
-- навіть якщо в коді з'явиться помилка.
-- ─────────────────────────────────────────────────────────────────────

ALTER TABLE "products"
  ADD CONSTRAINT "products_stock_on_hand_non_negative" CHECK ("stock_on_hand" >= 0),
  ADD CONSTRAINT "products_stock_reserved_non_negative" CHECK ("stock_reserved" >= 0),
  ADD CONSTRAINT "products_reserved_not_above_on_hand" CHECK ("stock_reserved" <= "stock_on_hand"),
  ADD CONSTRAINT "products_price_positive" CHECK ("price" > 0),
  ADD CONSTRAINT "products_pieces_positive" CHECK ("pieces" IS NULL OR "pieces" > 0),
  ADD CONSTRAINT "products_age_min_range" CHECK ("age_min" IS NULL OR ("age_min" >= 0 AND "age_min" <= 99)),
  ADD CONSTRAINT "products_low_stock_threshold_non_negative" CHECK ("low_stock_threshold" >= 0);

ALTER TABLE "order_items"
  ADD CONSTRAINT "order_items_quantity_positive" CHECK ("quantity" > 0),
  ADD CONSTRAINT "order_items_unit_price_positive" CHECK ("unit_price" > 0);

ALTER TABLE "orders"
  ADD CONSTRAINT "orders_total_amount_non_negative" CHECK ("total_amount" >= 0);

ALTER TABLE "customers"
  ADD CONSTRAINT "customers_total_spent_non_negative" CHECK ("total_spent" >= 0);

ALTER TABLE "checkouts"
  ADD CONSTRAINT "checkouts_quantity_positive" CHECK ("quantity" IS NULL OR "quantity" > 0);

-- Номери замовлень починаються зі 101.
ALTER SEQUENCE "orders_id_seq" RESTART WITH 101;
