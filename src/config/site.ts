export const siteConfig = {
  name: "Цеглинка",
  shortDescription: "Конструктори LEGO® з доставкою по Україні",
  description:
    "Інтернет-магазин конструкторів LEGO® «Цеглинка»: City, Technic, Friends, Creator, DUPLO та інші серії. Доставка Новою Поштою та Укрпоштою, оплата карткою або при отриманні.",
  url: (process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000").replace(/\/$/, ""),
  phone: "+380 44 000 00 00",
  email: "hello@tsehlynka.example",
  locale: "uk_UA",
} as const;

export function absoluteUrl(path = "/"): string {
  return `${siteConfig.url}${path.startsWith("/") ? path : `/${path}`}`;
}
