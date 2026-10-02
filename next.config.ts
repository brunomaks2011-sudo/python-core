import type { NextConfig } from "next";

const isProd = process.env.NODE_ENV === "production";

// Content Security Policy. 'unsafe-inline' для скриптів потрібен Next.js для гідратації
// без nonce (сторінки лишаються кешованими). Зовнішніх скриптів сайт не завантажує.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isProd ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://*.public.blob.vercel-storage.com",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  // Перенаправлення на сторінку оплати LiqPay після відправки форми
  "form-action 'self' https://www.liqpay.ua",
  "base-uri 'self'",
  "object-src 'none'",
  ...(isProd ? ["upgrade-insecure-requests"] : []),
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  // HSTS: браузер завжди відкриватиме сайт лише через HTTPS (2 роки)
  ...(isProd ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" }] : []),
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), browsing-topics=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  // Самодостатній бандл для Docker-образу (NEXT_OUTPUT=standalone задається в Dockerfile)
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  poweredByHeader: false,
  serverExternalPackages: ["@prisma/client", "bcryptjs"],
  experimental: {
    // Завантаження зображень товарів через Server Actions (до 10 МБ за раз)
    serverActions: { bodySizeLimit: "11mb" },
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
