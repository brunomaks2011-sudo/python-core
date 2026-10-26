import type { BoxState, Completeness, Product, ProductCondition } from "../generated/prisma/client.js";
import { Prisma, inTransaction, type PrismaClient, type Tx } from "../database/client.js";
import { NotFoundError, ValidationError } from "../lib/errors.js";
import { normalizeText, transliterationVariants } from "../lib/text.js";
import { detectTheme, themeSearchPattern } from "./themes.js";

export type Availability = "IN_STOCK" | "LOW_STOCK" | "OUT_OF_STOCK";

export interface ProductView extends Product {
  available: number;
  availability: Availability;
}

export function computeAvailability(
  p: Pick<Product, "stockOnHand" | "stockReserved" | "lowStockThreshold" | "status">,
): { available: number; availability: Availability } {
  const available = Math.max(0, p.stockOnHand - p.stockReserved);
  if (p.status !== "ACTIVE" || available <= 0) return { available: 0, availability: "OUT_OF_STOCK" };
  if (available <= p.lowStockThreshold) return { available, availability: "LOW_STOCK" };
  return { available, availability: "IN_STOCK" };
}

export function toView(p: Product): ProductView {
  return { ...p, ...computeAvailability(p) };
}

export type SortOrder = "relevance" | "price_asc" | "price_desc" | "newest" | "theme";

export interface SearchFilters {
  text?: string | null;
  theme?: string | null;
  /** Точна назва тематики (для каталогу з кнопками). */
  themeExact?: string | null;
  setNumber?: string | null;
  minPrice?: number | null;
  maxPrice?: number | null;
  /** Вік дитини: набори з рекомендованим віком «від N» не старше цього. */
  childAge?: number | null;
  condition?: ProductCondition | null;
  /** За замовчуванням покупцям показуються лише товари з доступним залишком. */
  onlyAvailable?: boolean;
  includeArchived?: boolean;
  sort?: SortOrder;
  limit?: number;
  offset?: number;
}

export interface SearchResult {
  items: ProductView[];
  total: number;
  /** Тематика, розпізнана в тексті запиту (якщо була). */
  detectedTheme: string | null;
}

const STOP_WORDS = new Set([
  "лего", "lego", "набір", "набори", "наборів", "набора", "наборі", "наборчик", "конструктор", "конструктори",
  "конструктора", "є", "чи", "у", "в", "вас", "покажи", "покажіть", "показати", "шукаю", "шукаємо", "хочу",
  "мені", "мене", "а", "і", "й", "та", "для", "до", "від", "з", "за", "на", "по", "про", "що", "який", "яка",
  "яке", "які", "щось", "ще", "будь", "ласка", "привіт", "добрий", "день", "вечір", "вітаю", "грн", "гривень",
  "гривні", "можна", "купити", "замовити", "ціна", "ціну", "скільки", "коштує", "коштують", "наявності",
  "наявність", "дитини", "дітей", "дитині", "хлопчика", "хлопчику", "дівчинки", "дівчинці", "років", "роки",
  "рік", "подарунок", "подарунка", "серія", "серії", "серію", "тематика", "тематики", "номер", "номером",
  "артикул", "недорогий", "недорого", "дешевий", "дешево", "новий", "нові", "нова", "вживаний", "вживані",
  "вживана", "бу", "б", "the", "is", "of", "a", "any", "set", "sets", "have", "you", "есть", "у вас", "или",
  "або", "чи є", "цей", "ця", "це", "ось", "там", "тут", "так", "ні", "ну", "мабуть", "можливо", "інші",
  "інший", "схожі", "схожий", "подібні", "варіанти", "варіант", "дешевше", "дорожче",
]);

/** Розбиває текст запиту на слова для пошуку (без службових слів і числових фільтрів). */
export function searchTokens(text: string): string[] {
  const tokens = normalizeText(text)
    .replace(/[.,+]/g, " ")
    .split(" ")
    .map((t) => t.replace(/^[-']+|[-']+$/g, ""))
    .filter((t) => t.length >= 2 && !STOP_WORDS.has(t))
    .filter((t) => !/^\d{1,2}$/.test(t));
  return [...new Set(tokens)].slice(0, 6);
}

function likePattern(value: string): string {
  return `%${value.replace(/[\\%_]/g, (c) => `\\${c}`)}%`;
}

export interface NewProductInput {
  name: string;
  setNumber: string | null;
  theme: string;
  pieces: number | null;
  ageMin: number | null;
  price: string;
  stock: number;
  condition: ProductCondition;
  boxState: BoxState;
  completeness: Completeness;
  conditionNote: string | null;
  imageUrl: string | null;
  telegramFileId: string | null;
  description: string | null;
  lowStockThreshold?: number;
}

export type EditableField =
  | "name"
  | "setNumber"
  | "theme"
  | "pieces"
  | "ageMin"
  | "price"
  | "condition"
  | "boxState"
  | "completeness"
  | "conditionNote"
  | "imageUrl"
  | "telegramFileId"
  | "description"
  | "lowStockThreshold";

export type ProductPatch = Partial<{
  name: string;
  setNumber: string | null;
  theme: string;
  pieces: number | null;
  ageMin: number | null;
  price: string;
  condition: ProductCondition;
  boxState: BoxState;
  completeness: Completeness;
  conditionNote: string | null;
  imageUrl: string | null;
  telegramFileId: string | null;
  description: string | null;
  lowStockThreshold: number;
}>;

function stringify(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (value instanceof Prisma.Decimal) return value.toFixed(2);
  return String(value);
}

export interface ThemeSummary {
  theme: string;
  availableCount: number;
  totalCount: number;
  minPrice: number | null;
}

export class ProductService {
  constructor(
    private readonly prisma: PrismaClient,
    private readonly defaults: { lowStockThreshold: number },
  ) {}

  async getById(id: number): Promise<ProductView | null> {
    const p = await this.prisma.product.findUnique({ where: { id } });
    return p ? toView(p) : null;
  }

  async getByIdOrThrow(id: number): Promise<ProductView> {
    const p = await this.getById(id);
    if (!p) throw new NotFoundError(`Товар #${id} не знайдено`);
    return p;
  }

  async getMany(ids: number[]): Promise<ProductView[]> {
    if (ids.length === 0) return [];
    const rows = await this.prisma.product.findMany({ where: { id: { in: ids } } });
    const byId = new Map(rows.map((r) => [r.id, toView(r)]));
    return ids.map((id) => byId.get(id)).filter((p): p is ProductView => Boolean(p));
  }

  /** Активні товари з указаним номером набору (новий і вживаний можуть бути окремими позиціями). */
  async findBySetNumber(setNumber: string, opts: { includeArchived?: boolean } = {}): Promise<ProductView[]> {
    const normalized = setNumber.trim().replace(/-1$/, "");
    const rows = await this.prisma.product.findMany({
      where: {
        setNumber: { equals: normalized, mode: "insensitive" },
        ...(opts.includeArchived ? {} : { status: "ACTIVE" }),
      },
      orderBy: [{ condition: "asc" }, { price: "asc" }],
    });
    return rows.map(toView);
  }

  async search(filters: SearchFilters): Promise<SearchResult> {
    const limit = Math.min(Math.max(filters.limit ?? 10, 1), 50);
    const offset = Math.max(filters.offset ?? 0, 0);
    const conditions: Prisma.Sql[] = [];
    let detectedTheme: string | null = null;
    let text = filters.text?.trim() ?? "";

    if (!filters.includeArchived) conditions.push(Prisma.sql`p.status = 'ACTIVE'`);
    if (filters.onlyAvailable !== false) conditions.push(Prisma.sql`(p.stock_on_hand - p.stock_reserved) > 0`);

    let themePattern = filters.theme ? themeSearchPattern(filters.theme) : null;
    if (!themePattern && text) {
      const detected = detectTheme(text);
      if (detected) {
        themePattern = detected.match;
        detectedTheme = detected.name;
        text = detected.rest;
      }
    } else if (filters.theme) {
      detectedTheme = detectTheme(filters.theme)?.name ?? filters.theme;
    }
    if (themePattern) conditions.push(Prisma.sql`p.theme ILIKE ${likePattern(themePattern)}`);
    if (filters.themeExact) {
      conditions.push(Prisma.sql`p.theme = ${filters.themeExact}`);
      detectedTheme = filters.themeExact;
    }

    if (filters.setNumber) {
      conditions.push(Prisma.sql`lower(p.set_number) = ${filters.setNumber.trim().replace(/-1$/, "").toLowerCase()}`);
    }
    if (filters.minPrice != null) conditions.push(Prisma.sql`p.price >= ${filters.minPrice}`);
    if (filters.maxPrice != null) conditions.push(Prisma.sql`p.price <= ${filters.maxPrice}`);
    if (filters.childAge != null) {
      conditions.push(Prisma.sql`p.age_min IS NOT NULL AND p.age_min <= ${filters.childAge}`);
    }
    if (filters.condition) conditions.push(Prisma.sql`p.condition = ${filters.condition}::"ProductCondition"`);

    const tokens = filters.setNumber ? [] : searchTokens(text);
    const tokenScores = tokens.map((token) => {
      const variants = [token, ...transliterationVariants(token)].map(likePattern);
      const perVariant = variants.map(
        (v) => Prisma.sql`(
          CASE WHEN p.name ILIKE ${v} THEN 4 ELSE 0 END +
          CASE WHEN p.theme ILIKE ${v} THEN 2 ELSE 0 END +
          CASE WHEN p.set_number ILIKE ${v} THEN 5 ELSE 0 END +
          CASE WHEN p.description ILIKE ${v} THEN 1 ELSE 0 END)`,
      );
      return perVariant.length === 1 ? perVariant[0]! : Prisma.sql`GREATEST(${Prisma.join(perVariant, ", ")})`;
    });
    const scoreExpr = tokenScores.length > 0 ? Prisma.join(tokenScores, " + ") : Prisma.sql`0`;
    const where = conditions.length > 0 ? Prisma.sql`WHERE ${Prisma.join(conditions, " AND ")}` : Prisma.empty;

    const sort = filters.sort ?? "relevance";
    const orderBy =
      sort === "price_asc"
        ? Prisma.sql`s.price ASC, s.id ASC`
        : sort === "price_desc"
          ? Prisma.sql`s.price DESC, s.id ASC`
          : sort === "newest"
            ? Prisma.sql`s.created_at DESC, s.id DESC`
            : sort === "theme"
              ? Prisma.sql`s.theme ASC, s.price ASC, s.id ASC`
              : tokens.length > 0
                ? Prisma.sql`s.score DESC, s.available DESC, s.price ASC, s.id ASC`
                : Prisma.sql`s.theme ASC, s.price ASC, s.id ASC`;

    const rows = await this.prisma.$queryRaw<Array<{ id: number; total: bigint }>>`
      SELECT s.id, COUNT(*) OVER() AS total
      FROM (
        SELECT p.id, p.price, p.created_at, p.theme,
               (p.stock_on_hand - p.stock_reserved) AS available,
               (${scoreExpr}) AS score
        FROM products p
        ${where}
      ) s
      ${tokens.length > 0 ? Prisma.sql`WHERE s.score >= ${Math.max(1, Math.ceil(tokens.length / 2))}` : Prisma.empty}
      ORDER BY ${orderBy}
      LIMIT ${limit} OFFSET ${offset}`;

    const items = await this.getMany(rows.map((r) => r.id));
    return { items, total: rows.length > 0 ? Number(rows[0]!.total) : 0, detectedTheme };
  }

  /** Тематики активних товарів із кількістю доступних позицій. */
  async listThemes(): Promise<ThemeSummary[]> {
    const rows = await this.prisma.$queryRaw<
      Array<{ theme: string; available_count: number; total_count: number; min_price: Prisma.Decimal | null }>
    >`
      SELECT theme,
             COUNT(*) FILTER (WHERE stock_on_hand - stock_reserved > 0)::int AS available_count,
             COUNT(*)::int AS total_count,
             MIN(price) FILTER (WHERE stock_on_hand - stock_reserved > 0) AS min_price
      FROM products
      WHERE status = 'ACTIVE'
      GROUP BY theme
      ORDER BY theme`;
    return rows.map((r) => ({
      theme: r.theme,
      availableCount: r.available_count,
      totalCount: r.total_count,
      minPrice: r.min_price === null ? null : Number(r.min_price),
    }));
  }

  /** Схожі доступні набори: та сама тематика, близька ціна. */
  async findSimilar(product: Pick<Product, "id" | "theme" | "price">, limit = 5): Promise<ProductView[]> {
    const rows = await this.prisma.$queryRaw<Array<{ id: number }>>`
      SELECT id FROM products
      WHERE status = 'ACTIVE' AND id <> ${product.id}
        AND (stock_on_hand - stock_reserved) > 0
        AND theme = ${product.theme}
      ORDER BY ABS(price - ${product.price}) ASC, id ASC
      LIMIT ${limit}`;
    let ids = rows.map((r) => r.id);
    if (ids.length < limit) {
      const more = await this.prisma.$queryRaw<Array<{ id: number }>>`
        SELECT id FROM products
        WHERE status = 'ACTIVE' AND id <> ${product.id}
          AND (stock_on_hand - stock_reserved) > 0
          AND theme <> ${product.theme}
        ORDER BY ABS(price - ${product.price}) ASC, id ASC
        LIMIT ${limit - ids.length}`;
      ids = [...ids, ...more.map((r) => r.id)];
    }
    return this.getMany(ids);
  }

  async listForAdmin(opts: { filter: "active" | "low" | "out" | "archived"; limit: number; offset: number }) {
    const statusCond = opts.filter === "archived" ? Prisma.sql`status = 'ARCHIVED'` : Prisma.sql`status = 'ACTIVE'`;
    const extra =
      opts.filter === "low"
        ? Prisma.sql`AND (stock_on_hand - stock_reserved) > 0 AND (stock_on_hand - stock_reserved) <= low_stock_threshold`
        : opts.filter === "out"
          ? Prisma.sql`AND (stock_on_hand - stock_reserved) <= 0`
          : Prisma.empty;
    const rows = await this.prisma.$queryRaw<Array<{ id: number; total: bigint }>>`
      SELECT id, COUNT(*) OVER() AS total FROM products
      WHERE ${statusCond} ${extra}
      ORDER BY theme ASC, name ASC, id ASC
      LIMIT ${opts.limit} OFFSET ${opts.offset}`;
    const items = await this.getMany(rows.map((r) => r.id));
    return { items, total: rows.length > 0 ? Number(rows[0]!.total) : 0 };
  }

  /** Товари, що закінчуються: доступний залишок <= порогу (включно з нулем). */
  async listLowStock(): Promise<ProductView[]> {
    const rows = await this.prisma.$queryRaw<Array<{ id: number }>>`
      SELECT id FROM products
      WHERE status = 'ACTIVE' AND (stock_on_hand - stock_reserved) <= low_stock_threshold
      ORDER BY (stock_on_hand - stock_reserved) ASC, theme ASC, name ASC`;
    return this.getMany(rows.map((r) => r.id));
  }

  /** Пошук для адміністратора: за id, номером набору або назвою (включно з архівом). */
  async adminLookup(query: string): Promise<ProductView[]> {
    const q = query.trim();
    if (/^#?\d{1,6}$/.test(q) && q.startsWith("#")) {
      const p = await this.getById(Number(q.slice(1)));
      return p ? [p] : [];
    }
    const bySet = await this.findBySetNumber(q, { includeArchived: true });
    if (bySet.length > 0) return bySet;
    if (/^\d{1,6}$/.test(q)) {
      const p = await this.getById(Number(q));
      if (p) return [p];
    }
    const result = await this.search({ text: q, onlyAvailable: false, includeArchived: true, limit: 10 });
    return result.items;
  }

  async create(input: NewProductInput, actorTelegramId: bigint): Promise<ProductView> {
    if (input.stock < 0) throw new ValidationError("Кількість не може бути від'ємною");
    return inTransaction(this.prisma, async (tx) => {
      const product = await tx.product.create({
        data: {
          name: input.name,
          setNumber: input.setNumber,
          theme: input.theme,
          pieces: input.pieces,
          ageMin: input.ageMin,
          price: new Prisma.Decimal(input.price),
          stockOnHand: input.stock,
          stockReserved: 0,
          lowStockThreshold: input.lowStockThreshold ?? this.defaults.lowStockThreshold,
          condition: input.condition,
          boxState: input.boxState,
          completeness: input.completeness,
          conditionNote: input.conditionNote,
          imageUrl: input.imageUrl,
          telegramFileId: input.telegramFileId,
          description: input.description,
        },
      });
      await tx.productChange.create({
        data: { productId: product.id, field: "created", oldValue: null, newValue: product.name, actorTelegramId },
      });
      if (input.stock > 0) {
        await tx.stockMovement.create({
          data: {
            productId: product.id,
            type: "INITIAL",
            onHandDelta: input.stock,
            reservedDelta: 0,
            onHandAfter: input.stock,
            reservedAfter: 0,
            actorType: "ADMIN",
            actorTelegramId,
            note: "Початковий залишок",
          },
        });
      }
      return toView(product);
    });
  }

  /** Оновлює поля товару й записує кожну зміну в історію (ціна, назва тощо). */
  async update(id: number, patch: ProductPatch, actorTelegramId: bigint): Promise<ProductView> {
    return inTransaction(this.prisma, async (tx) => {
      const current = await tx.product.findUnique({ where: { id } });
      if (!current) throw new NotFoundError(`Товар #${id} не знайдено`);
      const data: Prisma.ProductUpdateInput = {};
      const changes: Array<{ field: string; oldValue: string | null; newValue: string | null }> = [];
      for (const [key, raw] of Object.entries(patch) as Array<[keyof ProductPatch, unknown]>) {
        if (raw === undefined) continue;
        const next = key === "price" ? new Prisma.Decimal(raw as string) : raw;
        const before = stringify(current[key]);
        const after = stringify(next);
        if (before === after) continue;
        (data as Record<string, unknown>)[key] = next;
        changes.push({ field: key, oldValue: before, newValue: after });
      }
      if (changes.length === 0) return toView(current);
      const updated = await tx.product.update({ where: { id }, data });
      await tx.productChange.createMany({
        data: changes.map((c) => ({ ...c, productId: id, actorTelegramId })),
      });
      return toView(updated);
    });
  }

  async setStatus(id: number, status: "ACTIVE" | "ARCHIVED", actorTelegramId: bigint): Promise<ProductView> {
    return inTransaction(this.prisma, async (tx) => {
      const current = await tx.product.findUnique({ where: { id } });
      if (!current) throw new NotFoundError(`Товар #${id} не знайдено`);
      if (current.status === status) return toView(current);
      const updated = await tx.product.update({
        where: { id },
        data: { status, archivedAt: status === "ARCHIVED" ? new Date() : null },
      });
      await tx.productChange.create({
        data: { productId: id, field: "status", oldValue: current.status, newValue: status, actorTelegramId },
      });
      return toView(updated);
    });
  }

  async history(productId: number, limit = 20) {
    const [changes, movements] = await Promise.all([
      this.prisma.productChange.findMany({ where: { productId }, orderBy: { createdAt: "desc" }, take: limit }),
      this.prisma.stockMovement.findMany({ where: { productId }, orderBy: { createdAt: "desc" }, take: limit }),
    ]);
    return { changes, movements };
  }

  /** Для тестів і транзакцій: читання з блокуванням рядка. */
  static async lockById(tx: Tx, id: number): Promise<Product | null> {
    const rows = await tx.$queryRaw<Array<{ id: number }>>`SELECT id FROM products WHERE id = ${id} FOR UPDATE`;
    if (rows.length === 0) return null;
    return tx.product.findUnique({ where: { id } });
  }
}
