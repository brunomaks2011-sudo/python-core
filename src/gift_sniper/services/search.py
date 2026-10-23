"""On-demand search of current MRKT listings with a user filter (🔎 Поиск по фильтрам)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.domain.enums import FeedEventType
from gift_sniper.domain.types import Enrichment, ListingSnapshot, Share
from gift_sniper.integrations.mrkt import MrktClient, SalingQuery
from gift_sniper.services.enrichment import Enricher
from gift_sniper.services.filters import FilterSpec, MatchContext, evaluate
from gift_sniper.services.percentages import monochrome_listing_share

log = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchResult:
    items: list[tuple[ListingSnapshot, Enrichment]] = field(default_factory=list)
    scanned: int = 0
    matched: int = 0
    share: Share | None = None
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    exhausted: bool = True  # False when more MRKT pages were available


class SearchService:
    def __init__(
        self, mrkt: MrktClient, enricher: Enricher, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        self.mrkt = mrkt
        self.enricher = enricher
        self.sessionmaker = sessionmaker

    async def search(self, spec: FilterSpec, *, max_pages: int = 3, limit: int = 10) -> SearchResult:
        criteria = spec.criteria.model_copy(update={"only_new_listings": False})
        query = SalingQuery(
            collection_names=criteria.collections,
            model_names=criteria.models,
            backdrop_names=criteria.backdrops,
            symbol_names=criteria.symbols,
            ordering="Price",
            low_to_high=True,
        )
        result = SearchResult()
        matched: list[tuple[ListingSnapshot, Enrichment]] = []
        now = datetime.now(UTC)
        for _ in range(max_pages):
            listings, cursor = await self.mrkt.search_listings(query)
            result.scanned += len(listings)
            await self._record(listings)
            for listing in listings:
                enrichment = await self.enricher.enrich(listing)
                ctx = MatchContext(
                    event_type=FeedEventType.OBSERVED.value, detected_at=now, is_first_sighting=False
                )
                if evaluate(spec.kind, criteria, listing, enrichment, ctx).matched:
                    matched.append((listing, enrichment))
            too_expensive = (
                criteria.max_price_nano is not None
                and listings
                and all(
                    item.price_nano is not None and item.price_nano > criteria.max_price_nano
                    for item in listings
                )
            )
            if not cursor or not listings or too_expensive:
                break
            query.cursor = cursor
        else:
            result.exhausted = False
        result.matched = len(matched)
        result.share = monochrome_listing_share(e.verdict.status for _, e in matched) if matched else None
        result.items = sorted(matched, key=lambda m: m[0].price_nano or 0)[:limit]
        result.computed_at = datetime.now(UTC)
        return result

    async def _record(self, listings: list[ListingSnapshot]) -> None:
        """Search results are market observations too: keep them for statistics and price history."""
        try:
            async with self.sessionmaker() as session, session.begin():
                for item in listings:
                    if item.is_on_sale is False:
                        continue
                    verdict = self.enricher.classify(item)
                    await listings_repo.upsert_gift(session, item)
                    await listings_repo.observe_model(session, item)
                    await listings_repo.apply_event(
                        session,
                        FeedEventType.OBSERVED.value,
                        item,
                        price_nano=item.price_nano,
                        event_date=None,
                        source="saling",
                        source_event_id=None,
                        monochrome_status=verdict.status,
                    )
                    await listings_repo.set_classification(session, item.gift_id, verdict)
        except Exception:
            log.exception("failed to store search observations")
