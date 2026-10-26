"""HTTP server of the Mini App: the page itself and its JSON API.

Every API call carries Telegram's initData (`Authorization: tma <initData>`); only users allowed in the bot
(ADMIN_USER_IDS / ALLOWED_USER_IDS) get data, each only their own rules and limits.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from aiohttp import web
from pydantic import ValidationError

from gift_sniper.config import Settings
from gift_sniper.webapp.api import ApiError, MiniAppApi
from gift_sniper.webapp.auth import WebAppAuthError, WebAppIdentity, identify

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Неверные данные"
    field = ".".join(str(part) for part in errors[0]["loc"])
    return f"Неверное значение {field}: {errors[0]['msg']}"


def create_app(api: MiniAppApi, settings: Settings) -> web.Application:
    token = settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else ""
    max_age = timedelta(hours=settings.webapp_init_data_max_age_hours)
    registered: set[int] = set()

    @web.middleware
    async def errors(request: web.Request, handler: Handler) -> web.StreamResponse:
        try:
            response = await handler(request)
        except web.HTTPException:
            raise
        except WebAppAuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)
        except ApiError as exc:
            return web.json_response({"error": str(exc)}, status=exc.status)
        except ValidationError as exc:
            return web.json_response({"error": _validation_message(exc)}, status=400)
        except Exception:
            log.exception("Mini App request failed", extra={"path": request.path})
            return web.json_response({"error": "Внутренняя ошибка, подробности в логах бота"}, status=500)
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    async def caller(request: web.Request) -> int:
        header = request.headers.get("Authorization", "")
        identity: WebAppIdentity = identify(
            header[4:] if header.startswith("tma ") else "", bot_token=token, max_age=max_age
        )
        if not settings.is_allowed(identity.user_id):
            raise ApiError(
                f"Доступ запрещён. Попросите администратора добавить ваш ID: {identity.user_id}", 403
            )
        if identity.user_id not in registered:
            await api.register(identity)
            registered.add(identity.user_id)
        return identity.user_id

    async def body(request: web.Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except ValueError as exc:
            raise ApiError("Ожидался JSON") from exc
        if not isinstance(data, dict):
            raise ApiError("Ожидался объект JSON")
        return data

    def rule_id(request: web.Request) -> int:
        try:
            return int(request.match_info["rule_id"])
        except ValueError as exc:
            raise ApiError("Правило не найдено", 404) from exc

    async def index(_: web.Request) -> web.StreamResponse:
        return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    async def root(_: web.Request) -> web.StreamResponse:
        raise web.HTTPFound("/app/")

    async def me(request: web.Request) -> web.Response:
        return web.json_response(await api.me(await caller(request)))

    async def collections(request: web.Request) -> web.Response:
        return web.json_response(await api.collections(await caller(request)))

    async def collection(request: web.Request) -> web.Response:
        return web.json_response(await api.collection(await caller(request), request.match_info["name"]))

    async def save_picks(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(
            await api.save_picks(user_id, request.match_info["name"], await body(request))
        )

    async def rules(request: web.Request) -> web.Response:
        return web.json_response(await api.rules(await caller(request)))

    async def create_rule(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.create_rule(user_id, await body(request)), status=201)

    async def update_rule(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.update_rule(user_id, rule_id(request), await body(request)))

    async def delete_rule(request: web.Request) -> web.Response:
        await api.delete_rule(await caller(request), rule_id(request))
        return web.json_response({"ok": True})

    async def save_settings(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.save_settings(user_id, await body(request)))

    async def set_monochrome_mode(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.set_monochrome_mode(user_id, await body(request)))

    async def monochromes_everywhere(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.monochromes_everywhere(user_id, await body(request)))

    async def set_speed(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.set_speed(user_id, await body(request)))

    async def set_mode(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.set_mode(user_id, await body(request)))

    async def stop(request: web.Request) -> web.Response:
        return web.json_response(await api.emergency(await caller(request), stop=True))

    async def resume(request: web.Request) -> web.Response:
        return web.json_response(await api.emergency(await caller(request), stop=False))

    async def history(request: web.Request) -> web.Response:
        return web.json_response(await api.history(await caller(request)))

    async def prices(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.prices(user_id, await body(request)))

    async def market(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.market(user_id, await body(request)))

    async def leaders(request: web.Request) -> web.Response:
        user_id = await caller(request)
        try:
            days = int(request.query.get("days", "1"))
        except ValueError as exc:
            raise ApiError("Период — 1, 7 или 30 дней") from exc
        return web.json_response(await api.leaders(user_id, days))

    async def create_subscription(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.create_subscription(user_id, await body(request)), status=201)

    async def update_subscription(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(
            await api.update_subscription(user_id, rule_id(request), await body(request))
        )

    async def assistant(request: web.Request) -> web.Response:
        return web.json_response(await api.assistant(await caller(request)))

    async def save_assistant(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.save_assistant(user_id, await body(request)))

    async def list_position(request: web.Request) -> web.Response:
        user_id = await caller(request)
        try:
            position_id = int(request.match_info["position_id"])
        except ValueError as exc:
            raise ApiError("Позиция не найдена", 404) from exc
        return web.json_response(await api.list_position(user_id, position_id))

    async def my_orders(request: web.Request) -> web.Response:
        return web.json_response(await api.my_orders(await caller(request)))

    async def market_orders(request: web.Request) -> web.Response:
        user_id = await caller(request)
        q = request.query
        return web.json_response(
            await api.market_orders(user_id, q.get("collection", ""), q.get("model"), q.get("backdrop"))
        )

    async def outbid(request: web.Request) -> web.Response:
        user_id = await caller(request)
        return web.json_response(await api.outbid(user_id, await body(request)))

    app = web.Application(middlewares=[errors], client_max_size=64 * 1024)
    app.router.add_get("/", root)
    app.router.add_get("/app/", index)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/collections", collections)
    app.router.add_get("/api/collections/{name}", collection)
    app.router.add_put("/api/collections/{name}/picks", save_picks)
    app.router.add_put("/api/monochromes", monochromes_everywhere)
    app.router.add_put("/api/monochrome-mode", set_monochrome_mode)
    app.router.add_get("/api/rules", rules)
    app.router.add_post("/api/rules", create_rule)
    app.router.add_put("/api/rules/{rule_id}", update_rule)
    app.router.add_patch("/api/rules/{rule_id}", update_rule)
    app.router.add_delete("/api/rules/{rule_id}", delete_rule)
    app.router.add_put("/api/settings", save_settings)
    app.router.add_put("/api/mode", set_mode)
    app.router.add_put("/api/speed", set_speed)
    app.router.add_post("/api/stop", stop)
    app.router.add_post("/api/resume", resume)
    app.router.add_get("/api/history", history)
    app.router.add_post("/api/prices", prices)
    app.router.add_post("/api/market", market)
    app.router.add_get("/api/leaders", leaders)
    app.router.add_post("/api/subscriptions", create_subscription)
    app.router.add_put("/api/subscriptions/{rule_id}", update_subscription)
    app.router.add_get("/api/assistant", assistant)
    app.router.add_put("/api/assistant", save_assistant)
    app.router.add_post("/api/assistant/positions/{position_id}/list", list_position)
    app.router.add_get("/api/orders/mine", my_orders)
    app.router.add_get("/api/orders/market", market_orders)
    app.router.add_post("/api/orders/outbid", outbid)
    return app


async def start_webapp_server(api: MiniAppApi, settings: Settings) -> web.AppRunner:
    runner = web.AppRunner(create_app(api, settings), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, settings.webapp_host, settings.webapp_port).start()
    log.info("Mini App server started", extra={"host": settings.webapp_host, "port": settings.webapp_port})
    return runner
