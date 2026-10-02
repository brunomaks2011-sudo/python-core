import type { NextAuthConfig } from "next-auth";

/**
 * Базова конфігурація Auth.js без залежностей від БД — її можна імпортувати
 * у proxy (middleware). Провайдери додаються в src/auth.ts.
 */
export const authConfig = {
  pages: { signIn: "/login" },
  session: { strategy: "jwt", maxAge: 30 * 24 * 60 * 60 },
  trustHost: true,
  providers: [],
  callbacks: {
    jwt({ token, user }) {
      if (user) {
        token.id = user.id;
        token.role = user.role ?? "USER";
      }
      return token;
    },
    session({ session, token }) {
      if (token.id) session.user.id = token.id;
      session.user.role = token.role ?? "USER";
      return session;
    },
  },
} satisfies NextAuthConfig;
