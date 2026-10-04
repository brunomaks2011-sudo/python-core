import NextAuth, { CredentialsSignin } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";
import { authConfig } from "@/auth.config";
import { prisma } from "@/lib/prisma";
import { loginSchema } from "@/lib/validation";
import { clientIp, rateLimit, releaseRateLimit, resetRateLimit } from "@/lib/rate-limit";

export class RateLimitedError extends CredentialsSignin {
  code = "rate_limited";
}

// Ліміти на спроби входу: на пару IP+email і окремо на IP
const LOGIN_WINDOW_MS = 15 * 60 * 1000;
const LOGIN_LIMIT_PER_ACCOUNT = 5;
const LOGIN_LIMIT_PER_IP = 30;

// Хеш-«пустушка» для вирівнювання часу відповіді, коли користувача не існує
const DUMMY_HASH = "$2b$12$9.WVAMeMNNZ7gxj.HuuUTuLrGiGHVX9IjoiHK6.G2eJuECftsS0I.";

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [
    Credentials({
      credentials: { email: { label: "Email" }, password: { label: "Пароль", type: "password" } },
      async authorize(raw, request) {
        const parsed = loginSchema.safeParse(raw);
        if (!parsed.success) return null;
        const { email, password } = parsed.data;

        const ip = request ? clientIp(request.headers) : "unknown";
        const accountKey = `login:${ip}:${email}`;
        const ipKey = `login-ip:${ip}`;
        const [perAccount, perIp] = await Promise.all([
          rateLimit(accountKey, LOGIN_LIMIT_PER_ACCOUNT, LOGIN_WINDOW_MS),
          rateLimit(ipKey, LOGIN_LIMIT_PER_IP, LOGIN_WINDOW_MS),
        ]);
        if (!perAccount.ok || !perIp.ok) throw new RateLimitedError();

        const user = await prisma.user.findUnique({ where: { email } });
        const valid = await bcrypt.compare(password, user?.passwordHash ?? DUMMY_HASH);
        if (!user || !valid) return null;

        // Успішний вхід не витрачає ліміти
        await Promise.all([resetRateLimit(accountKey), releaseRateLimit(ipKey)]);
        return { id: user.id, email: user.email, name: user.name, role: user.role };
      },
    }),
  ],
});
