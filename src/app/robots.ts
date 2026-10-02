import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/config/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/admin", "/account", "/cart", "/checkout", "/order/", "/payment/", "/api/", "/login", "/register", "/forgot-password", "/reset-password"],
      },
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
  };
}
