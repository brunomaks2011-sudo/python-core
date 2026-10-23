from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from gift_sniper.bot.handlers import build_router
from gift_sniper.bot.middlewares import AccessMiddleware
from gift_sniper.services.container import Services


def build_dispatcher(services: Services) -> Dispatcher:
    storage = RedisStorage(services.redis)
    dispatcher = Dispatcher(storage=storage)
    access = AccessMiddleware(services)
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)
    dispatcher.include_router(build_router())
    return dispatcher
