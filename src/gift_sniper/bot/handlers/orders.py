"""📋 Outbidding an MRKT order from the alert "your order was outbid" in one tap."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from gift_sniper.domain.money import format_ton
from gift_sniper.services.container import Services

router = Router(name="orders")

ICON = {"done": "✅", "dry_run": "🧪", "moved": "↗️", "lost": "⚠️", "unconfirmed": "❓", "refused": "🚫"}


@router.callback_query(F.data.startswith("ob:"))
async def cb_outbid(callback: CallbackQuery, services: Services, can_purchase: bool) -> None:
    token = (callback.data or "")[3:]
    payload = await services.notifier.read_token(token)
    if payload is None or services.orders is None or not can_purchase:
        await callback.answer("Кнопка устарела или недоступна", show_alert=True)
        return
    # one action per button: a second tap does nothing
    if not await services.redis.delete(f"{services.settings.redis_prefix}:btn:{token}"):
        await callback.answer("Уже выполняется или выполнено", show_alert=True)
        return
    await callback.answer("⏳ Перебиваю ордер…")
    result = await services.orders.outbid(
        user_id=callback.from_user.id, order_id=str(payload["order_id"]), price_nano=int(payload["price"])
    )
    keyboard = None
    if result.status == "moved" and result.price_nano is not None:
        again = await services.notifier.make_token(
            {"order_id": payload["order_id"], "price": result.price_nano}, ttl=24 * 3600
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"⚡ Перебить → {format_ton(result.price_nano)}", callback_data=f"ob:{again}"
                    )
                ]
            ]
        )
    if callback.message is not None:
        await callback.message.answer(
            f"{ICON.get(result.status, '')} {escape(result.text)}", reply_markup=keyboard
        )
