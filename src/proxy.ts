import NextAuth from "next-auth";
import { NextResponse } from "next/server";
import { authConfig } from "@/auth.config";

// Next.js 16: proxy.ts (колишній middleware.ts).
// Перший рубіж: редирект неавторизованих з /account і /admin.
// Остаточна перевірка ролі виконується на сервері в кожній адмінській сторінці/дії (requireAdmin).
const { auth } = NextAuth(authConfig);

export default auth((req) => {
  const { pathname, search } = req.nextUrl;

  // Примусовий HTTPS за reverse-proxy. На Vercel і з Caddy редирект http→https уже робить платформа,
  // тож це резервний механізм, який вмикається змінною FORCE_HTTPS=1.
  if (process.env.FORCE_HTTPS === "1" && req.headers.get("x-forwarded-proto") === "http") {
    const url = req.nextUrl.clone();
    url.protocol = "https:";
    url.port = "";
    return NextResponse.redirect(url, 308);
  }

  const needsAuth = pathname.startsWith("/account") || pathname.startsWith("/admin");
  if (needsAuth && !req.auth?.user) {
    const login = new URL("/login", req.nextUrl.origin);
    login.searchParams.set("callbackUrl", pathname + search);
    return NextResponse.redirect(login);
  }
  if (pathname.startsWith("/admin") && req.auth?.user?.role !== "ADMIN") {
    return NextResponse.rewrite(new URL("/404", req.nextUrl.origin), { status: 404 });
  }
  return NextResponse.next();
});

export const config = {
  // Пропускаємо статику, зображення та webhook платіжної системи
  matcher: ["/((?!_next/static|_next/image|images/|uploads/|api/payments|favicon.ico|icon.svg|robots.txt|sitemap.xml|og.png).*)"],
};
