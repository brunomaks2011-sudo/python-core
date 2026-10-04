import "server-only";
import nodemailer from "nodemailer";

type Mail = { to: string; subject: string; text: string; html?: string };

let transporter: nodemailer.Transporter | null = null;

/** Надсилає лист через SMTP. Без SMTP_HOST лист виводиться в консоль (режим розробки). */
export async function sendMail(mail: Mail): Promise<void> {
  if (!process.env.SMTP_HOST) {
    console.info(`[mail] (SMTP не налаштовано) → ${mail.to}: ${mail.subject}\n${mail.text}`);
    return;
  }
  transporter ??= nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: Number(process.env.SMTP_PORT || 587),
    secure: Number(process.env.SMTP_PORT) === 465,
    auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASSWORD } : undefined,
  });
  try {
    await transporter.sendMail({ from: process.env.MAIL_FROM || "no-reply@example.com", ...mail });
  } catch (e) {
    // Помилка пошти не повинна ламати оформлення замовлення
    console.error("[mail] send failed:", (e as Error).message);
  }
}
