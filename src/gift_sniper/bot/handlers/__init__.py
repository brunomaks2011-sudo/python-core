from aiogram import Router

from gift_sniper.bot.handlers import common, filters, market, modes, orders, settings, wiki

_MODULE_ROUTERS = [
    common.router,
    filters.router,
    modes.router,
    market.router,
    orders.router,
    wiki.router,
    settings.router,
]


def build_router() -> Router:
    """Root router with all handlers. Safe to call more than once (e.g. a restarted dispatcher)."""
    root = Router(name="root")
    for sub in _MODULE_ROUTERS:
        parent = sub.parent_router
        if parent is not None:  # detach from a previous dispatcher before re-attaching
            parent.sub_routers.remove(sub)
            sub._parent_router = None
    root.include_routers(*_MODULE_ROUTERS)
    return root
