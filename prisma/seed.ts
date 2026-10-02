/**
 * Наповнення бази тестовими даними: категорії, 26 товарів, адміністратор, налаштування.
 * Запуск: npm run db:seed
 * Дані адміністратора беруться з .env (ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME).
 * Скрипт ідемпотентний — повторний запуск оновлює записи, а не дублює їх.
 */
import { PrismaClient } from "@prisma/client";
import bcrypt from "bcryptjs";

const prisma = new PrismaClient();

const uah = (n: number) => Math.round(n * 100);

const categories = [
  { slug: "city", name: "City", description: "Місто, рятувальники, поліція та транспорт.", sortOrder: 1 },
  { slug: "technic", name: "Technic", description: "Складні механізми, шестерні та справжня інженерія.", sortOrder: 2 },
  { slug: "friends", name: "Friends", description: "Затишні будиночки та пригоди друзів.", sortOrder: 3 },
  { slug: "creator", name: "Creator 3-в-1", description: "Три моделі з одного набору.", sortOrder: 4 },
  { slug: "duplo", name: "DUPLO", description: "Великі деталі для найменших будівничих.", sortOrder: 5 },
  { slug: "classic", name: "Classic", description: "Креативні коробки з деталями для фантазії.", sortOrder: 6 },
];

type SeedProduct = {
  name: string;
  slug: string;
  sku: string;
  category: string;
  price: number;
  oldPrice?: number;
  stock: number;
  pieces: number;
  ageMin: number;
  weightGrams: number;
  scene: string;
  featured?: boolean;
  salesCount?: number;
  isActive?: boolean;
  daysAgo: number;
  description: string;
};

const products: SeedProduct[] = [
  { name: "Пожежна станція", slug: "pozhezhna-stantsiia-60401", sku: "60401", category: "city", price: 2899, oldPrice: 3299, stock: 12, pieces: 540, ageMin: 6, weightGrams: 1300, scene: "city", featured: true, salesCount: 140, daysAgo: 40, description: "Велика пожежна станція з гаражем, пожежною машиною з висувною драбиною та трьома мініфігурками рятувальників. Розгорни будівлю, щоб грати всередині." },
  { name: "Поліцейський патрульний автомобіль", slug: "politseiskyi-avtomobil-60402", sku: "60402", category: "city", price: 649, stock: 30, pieces: 94, ageMin: 5, weightGrams: 300, scene: "car", salesCount: 210, daysAgo: 80, description: "Компактний патрульний автомобіль з мигалками на даху та мініфігуркою поліцейського. Чудовий перший набір серії City." },
  { name: "Вантажний потяг", slug: "vantazhnyi-potiah-60403", sku: "60403", category: "city", price: 7499, oldPrice: 7999, stock: 4, pieces: 1150, ageMin: 7, weightGrams: 2900, scene: "train", featured: true, salesCount: 55, daysAgo: 20, description: "Потяг з локомотивом, двома вагонами, краном і 20 секціями колії. Підтримує керування з пульта (батарейки не входять)." },
  { name: "Космічна ракета дослідників", slug: "kosmichna-raketa-60404", sku: "60404", category: "city", price: 3499, stock: 9, pieces: 810, ageMin: 7, weightGrams: 1500, scene: "rocket", featured: true, salesCount: 98, daysAgo: 5, description: "Багатоступенева ракета зі стартовим майданчиком, центром керування польотом і марсоходом. Відкривай нові світи разом з командою астронавтів." },
  { name: "Морський рятувальний катер", slug: "riatuvalnyi-kater-60405", sku: "60405", category: "city", price: 1599, stock: 0, pieces: 280, ageMin: 6, weightGrams: 700, scene: "ship", salesCount: 77, daysAgo: 60, description: "Швидкісний рятувальний катер з кабіною, рятувальним кругом і двома водолазами. Тримається на воді!" },
  { name: "Пасажирський літак", slug: "pasazhyrskyi-litak-60406", sku: "60406", category: "city", price: 3999, oldPrice: 4499, stock: 7, pieces: 913, ageMin: 7, weightGrams: 1700, scene: "plane", salesCount: 61, daysAgo: 2, description: "Пасажирський літак з кабіною пілотів, салоном на 8 місць, трапом і терміналом аеропорту." },

  { name: "Гоночний суперкар", slug: "honochnyi-superkar-42201", sku: "42201", category: "technic", price: 5999, stock: 6, pieces: 1432, ageMin: 10, weightGrams: 2100, scene: "car", featured: true, salesCount: 88, daysAgo: 14, description: "Детальна модель суперкара з робочою коробкою передач, двигуном V8 з рухомими поршнями та підвіскою на всіх колесах." },
  { name: "Гусеничний екскаватор", slug: "husenychnyi-ekskavator-42202", sku: "42202", category: "technic", price: 4299, stock: 11, pieces: 1050, ageMin: 9, weightGrams: 1800, scene: "technic", salesCount: 64, daysAgo: 35, description: "Екскаватор з поворотною платформою, функціональним ковшем і гусеницями. Механізми керуються шестернями." },
  { name: "Робот-трансформер", slug: "robot-transformer-42203", sku: "42203", category: "technic", price: 2499, oldPrice: 2899, stock: 15, pieces: 620, ageMin: 9, weightGrams: 900, scene: "robot", salesCount: 120, daysAgo: 25, description: "Робот, що перетворюється на всюдихід. Шарнірні кінцівки та рухомий торс." },
  { name: "Вертоліт рятувальників", slug: "vertolit-riatuvalnykiv-42204", sku: "42204", category: "technic", price: 3199, stock: 3, pieces: 830, ageMin: 9, weightGrams: 1200, scene: "plane", salesCount: 40, daysAgo: 9, description: "Вертоліт з обертовими гвинтами, лебідкою та відкидними дверима. Гвинти обертаються від колеса на корпусі." },
  { name: "Мотоцикл-спорт", slug: "motocykl-sport-42205", sku: "42205", category: "technic", price: 1899, stock: 20, pieces: 450, ageMin: 9, weightGrams: 700, scene: "technic", salesCount: 72, daysAgo: 70, description: "Спортивний мотоцикл з робочою коробкою передач і двоциліндровим двигуном." },

  { name: "Будиночок біля озера", slug: "budynochok-bilia-ozera-41801", sku: "41801", category: "friends", price: 2699, stock: 10, pieces: 520, ageMin: 7, weightGrams: 1100, scene: "house", featured: true, salesCount: 160, daysAgo: 18, description: "Затишний будиночок з терасою, каяком і містком до озера. У наборі дві мініляльки та кошеня." },
  { name: "Кафе-кондитерська", slug: "kafe-kondyterska-41802", sku: "41802", category: "friends", price: 1499, oldPrice: 1799, stock: 18, pieces: 340, ageMin: 6, weightGrams: 650, scene: "house", salesCount: 190, daysAgo: 45, description: "Кафе з вітриною тістечок, кавоваркою та літнім майданчиком." },
  { name: "Ветеринарна клініка", slug: "veterynarna-klinika-41803", sku: "41803", category: "friends", price: 2199, stock: 2, pieces: 470, ageMin: 6, weightGrams: 950, scene: "house", salesCount: 95, daysAgo: 12, description: "Клініка для тварин з оглядовою кімнатою, рентгеном і машиною швидкої допомоги." },
  { name: "Шкільний автобус друзів", slug: "shkilnyi-avtobus-41804", sku: "41804", category: "friends", price: 1299, stock: 14, pieces: 290, ageMin: 6, weightGrams: 550, scene: "car", salesCount: 50, daysAgo: 3, description: "Яскравий шкільний автобус з відкидним дахом і місцем для чотирьох мініляльок." },

  { name: "Вогняний дракон 3-в-1", slug: "vohnianyi-drakon-31201", sku: "31201", category: "creator", price: 1999, stock: 16, pieces: 480, ageMin: 8, weightGrams: 800, scene: "dragon", featured: true, salesCount: 175, daysAgo: 28, description: "Збери дракона, морського змія або фенікса. Рухомі крила, шия та хвіст." },
  { name: "Середньовічний замок 3-в-1", slug: "serednovichnyi-zamok-31202", sku: "31202", category: "creator", price: 4799, oldPrice: 5299, stock: 5, pieces: 1420, ageMin: 9, weightGrams: 2200, scene: "castle", salesCount: 58, daysAgo: 7, description: "Замок з підйомним мостом, вежами та катапультою. Перебудуй у ринкову площу або вартову вежу." },
  { name: "Ретро-літак 3-в-1", slug: "retro-litak-31203", sku: "31203", category: "creator", price: 1199, stock: 22, pieces: 260, ageMin: 7, weightGrams: 450, scene: "plane", salesCount: 66, daysAgo: 55, description: "Біплан, гелікоптер або вітрильник — обирай, що збудувати сьогодні." },
  { name: "Космічний робот 3-в-1", slug: "kosmichnyi-robot-31204", sku: "31204", category: "creator", price: 899, stock: 25, pieces: 180, ageMin: 7, weightGrams: 350, scene: "robot", salesCount: 102, daysAgo: 1, description: "Робот, космічний пес або винищувач. Шарнірні руки та ноги." },
  { name: "Вітрильний корабель 3-в-1", slug: "vitrylnyi-korabel-31205", sku: "31205", category: "creator", price: 2599, stock: 8, pieces: 650, ageMin: 8, weightGrams: 1000, scene: "ship", salesCount: 33, daysAgo: 30, description: "Корабель з вітрилами, що розгортаються, гарматами та каютою капітана.", isActive: false },

  { name: "Мій перший потяг DUPLO", slug: "mii-pershyi-potiah-10901", sku: "10901", category: "duplo", price: 1099, stock: 17, pieces: 34, ageMin: 2, weightGrams: 800, scene: "train", featured: true, salesCount: 230, daysAgo: 50, description: "Великі яскраві деталі, потяг з вагончиками та тваринки. Розвиває моторику та уяву." },
  { name: "Ферма з тваринами DUPLO", slug: "ferma-z-tvarynamy-10902", sku: "10902", category: "duplo", price: 1399, oldPrice: 1599, stock: 9, pieces: 58, ageMin: 2, weightGrams: 1000, scene: "house", salesCount: 145, daysAgo: 22, description: "Ферма з коровою, конячкою та курочками. Відкривається, щоб зручно гратися." },
  { name: "Цифри та кольори DUPLO", slug: "tsyfry-ta-kolory-10903", sku: "10903", category: "duplo", price: 699, stock: 40, pieces: 30, ageMin: 1, weightGrams: 600, scene: "stack", salesCount: 85, daysAgo: 4, description: "Вивчаємо цифри від 1 до 10 та кольори, будуючи веселі вежі." },

  { name: "Велика креативна коробка", slug: "velyka-kreatyvna-korobka-11701", sku: "11701", category: "classic", price: 1899, stock: 13, pieces: 790, ageMin: 4, weightGrams: 1400, scene: "stack", featured: true, salesCount: 200, daysAgo: 65, description: "790 деталей 33 кольорів, вікна, двері та колеса. Інструкції до кількох моделей для старту." },
  { name: "Базова пластина зелена", slug: "bazova-plastyna-11702", sku: "11702", category: "classic", price: 349, stock: 60, pieces: 1, ageMin: 4, weightGrams: 150, scene: "stack", salesCount: 300, daysAgo: 90, description: "Пластина 32×32 для будівництва власного міста або саду." },
  { name: "Цеглинки та колеса", slug: "tsehlynky-ta-kolesa-11703", sku: "11703", category: "classic", price: 799, oldPrice: 949, stock: 1, pieces: 300, ageMin: 4, weightGrams: 500, scene: "car", salesCount: 70, daysAgo: 10, description: "Набір деталей з колесами для створення власних машин і візків." },
];

async function main() {
  // ---- Налаштування магазину ----
  await prisma.storeSettings.upsert({
    where: { id: 1 },
    update: {},
    create: {
      id: 1,
      freeShippingThreshold: uah(Number(process.env.FREE_SHIPPING_THRESHOLD_UAH ?? 2000)),
      ukrposhtaRate: uah(Number(process.env.UKRPOSHTA_RATE_UAH ?? 60)),
      npWarehouseFallbackRate: uah(Number(process.env.NP_FALLBACK_WAREHOUSE_RATE_UAH ?? 80)),
      npCourierFallbackRate: uah(Number(process.env.NP_FALLBACK_COURIER_RATE_UAH ?? 120)),
    },
  });

  // ---- Категорії ----
  const categoryIds: Record<string, string> = {};
  for (const c of categories) {
    const row = await prisma.category.upsert({
      where: { slug: c.slug },
      update: { name: c.name, description: c.description, sortOrder: c.sortOrder },
      create: { ...c, image: `/images/categories/${c.slug}.svg` },
    });
    categoryIds[c.slug] = row.id;
  }

  // ---- Товари ----
  for (const p of products) {
    const images = [1, 2, 3].map((v) => `/images/products/${p.scene}-${v}.svg`);
    const data = {
      name: p.name,
      slug: p.slug,
      sku: p.sku,
      description: p.description,
      price: uah(p.price),
      oldPrice: p.oldPrice ? uah(p.oldPrice) : null,
      stock: p.stock,
      pieces: p.pieces,
      ageMin: p.ageMin,
      weightGrams: p.weightGrams,
      images,
      isActive: p.isActive ?? true,
      isFeatured: p.featured ?? false,
      salesCount: p.salesCount ?? 0,
      categoryId: categoryIds[p.category],
      createdAt: new Date(Date.now() - p.daysAgo * 24 * 60 * 60 * 1000),
    };
    await prisma.product.upsert({ where: { sku: p.sku }, update: data, create: data });
  }

  // ---- Адміністратор ----
  const email = process.env.ADMIN_EMAIL?.trim().toLowerCase();
  const password = process.env.ADMIN_PASSWORD;
  if (!email || !password) {
    console.warn("⚠️  ADMIN_EMAIL або ADMIN_PASSWORD не задані в .env — адміністратора не створено.");
  } else if (password.length < 8) {
    throw new Error("ADMIN_PASSWORD має містити щонайменше 8 символів");
  } else {
    const passwordHash = await bcrypt.hash(password, 12);
    await prisma.user.upsert({
      where: { email },
      update: { role: "ADMIN", passwordHash, name: process.env.ADMIN_NAME || "Адміністратор" },
      create: { email, passwordHash, role: "ADMIN", name: process.env.ADMIN_NAME || "Адміністратор" },
    });
    console.log(`👤 Адміністратор: ${email}`);
  }

  console.log(`✅ Категорій: ${categories.length}, товарів: ${products.length}`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
