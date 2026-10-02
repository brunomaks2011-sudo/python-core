import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Мінімальний самодостатній бандл для Docker-образу
  output: "standalone",
  poweredByHeader: false,
  serverExternalPackages: ["@prisma/client", "bcryptjs"],
  experimental: {
    // Завантаження зображень товарів через Server Actions (до 10 МБ за раз)
    serverActions: { bodySizeLimit: "11mb" },
  },
};

export default nextConfig;
