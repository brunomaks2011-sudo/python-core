import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Мінімальний самодостатній бандл для Docker-образу
  output: "standalone",
  poweredByHeader: false,
  serverExternalPackages: ["@prisma/client", "bcryptjs"],
};

export default nextConfig;
