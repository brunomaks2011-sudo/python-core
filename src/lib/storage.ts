import "server-only";
import { randomBytes } from "node:crypto";
import { mkdir, writeFile, unlink } from "node:fs/promises";
import path from "node:path";

export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

const SIGNATURES: { ext: string; mime: string; test: (b: Buffer) => boolean }[] = [
  { ext: "jpg", mime: "image/jpeg", test: (b) => b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff },
  { ext: "png", mime: "image/png", test: (b) => b.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) },
  { ext: "webp", mime: "image/webp", test: (b) => b.subarray(0, 4).toString() === "RIFF" && b.subarray(8, 12).toString() === "WEBP" },
  { ext: "avif", mime: "image/avif", test: (b) => b.subarray(4, 12).toString() === "ftypavif" },
];

export const MIME_BY_EXT: Record<string, string> = Object.fromEntries(SIGNATURES.map((s) => [s.ext, s.mime]));

export class UploadError extends Error {}

/**
 * Визначає тип зображення за «магічними байтами», а не за розширенням чи заголовком клієнта.
 * SVG навмисно не приймається (може містити скрипти).
 */
export function detectImageType(buf: Buffer) {
  return SIGNATURES.find((s) => s.test(buf)) ?? null;
}

export function uploadDir(): string {
  return path.resolve(process.env.UPLOAD_DIR || "./uploads");
}

/** Зберігає зображення і повертає публічний URL. Vercel Blob — якщо задано BLOB_READ_WRITE_TOKEN, інакше локальний диск. */
export async function saveImage(file: File): Promise<string> {
  if (file.size === 0) throw new UploadError("Порожній файл");
  if (file.size > MAX_IMAGE_BYTES) throw new UploadError(`Файл «${file.name}» більший за 5 МБ`);
  const buf = Buffer.from(await file.arrayBuffer());
  const type = detectImageType(buf);
  if (!type) throw new UploadError(`«${file.name}»: дозволені лише JPG, PNG, WEBP, AVIF`);
  const name = `${Date.now().toString(36)}-${randomBytes(8).toString("hex")}.${type.ext}`;

  if (process.env.BLOB_READ_WRITE_TOKEN) {
    const { put } = await import("@vercel/blob");
    const blob = await put(`products/${name}`, buf, { access: "public", contentType: type.mime });
    return blob.url;
  }
  const dir = path.join(uploadDir(), "products");
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, name), buf);
  return `/uploads/products/${name}`;
}

/** Видаляє завантажений файл (тільки наші файли; заглушки з /images не чіпаємо). */
export async function deleteImage(url: string): Promise<void> {
  try {
    if (url.startsWith("/uploads/products/")) {
      const file = path.join(uploadDir(), "products", path.basename(url));
      await unlink(file);
    } else if (process.env.BLOB_READ_WRITE_TOKEN && url.includes(".blob.vercel-storage.com/")) {
      const { del } = await import("@vercel/blob");
      await del(url);
    }
  } catch {
    // файл міг бути вже видалений
  }
}
