"""Service container shared by the bot handlers and background workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import Settings
from gift_sniper.integrations.giftwiki import GiftWikiClient
from gift_sniper.integrations.mrkt import MrktClient
from gift_sniper.services.control import ControlService
from gift_sniper.services.enrichment import Enricher, ReferenceStore
from gift_sniper.services.filter_cache import FilterCache
from gift_sniper.services.giftwiki_sync import GiftWikiSync
from gift_sniper.services.monitor import ListingMonitor
from gift_sniper.services.notifications import Notifier
from gift_sniper.services.orders import OrdersService
from gift_sniper.services.purchase import PurchaseService
from gift_sniper.services.resale import ResaleAssistant
from gift_sniper.services.search import SearchService
from gift_sniper.services.stats import StatsService


@dataclass
class Services:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    mrkt: MrktClient
    giftwiki: GiftWikiClient
    control: ControlService
    store: ReferenceStore
    enricher: Enricher
    filter_cache: FilterCache
    notifier: Notifier
    purchase: PurchaseService
    search: SearchService
    stats: StatsService
    sync: GiftWikiSync
    monitor: ListingMonitor | None = None
    purchase_queue: Any = None
    events_queue: Any = None
    resale: ResaleAssistant | None = None
    orders: OrdersService | None = None
