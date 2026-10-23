"""Gift Wiki synchronization into PostgreSQL and its effect on classification."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from gift_sniper.db.models import GiftWikiAttribute, GiftWikiMonochrome, GiftWikiSyncRun
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.domain.enums import MonochromeStatus
from gift_sniper.domain.types import MonochromeRecord
from gift_sniper.integrations.giftwiki import PAGE_SIZE, GiftWikiError, GiftWikiForbiddenError
from gift_sniper.services.giftwiki_sync import GiftWikiSync
from tests.factories import make_listing
from tests.integration.conftest import Env

pytestmark = pytest.mark.db


def rec(
    i: int, gift: str, model: str, backdrop: str, kind: str = "high", gift_id: str | None = None
) -> MonochromeRecord:
    return MonochromeRecord(
        record_id=f"{gift}-{i}",
        gift_id=gift_id or f"id-{gift}",
        gift_name=gift,
        model_name=model,
        backdrop_name=backdrop,
        type_raw=kind,
        center_color="#000000",
        raw={"_id": f"{gift}-{i}", "x": 1},
    )


class FakeGiftWiki:
    configured = True

    def __init__(
        self, records: list[MonochromeRecord], *, fail: bool = False, forbid_lookup: bool = False
    ) -> None:
        self.records = records
        self.fail = fail
        self.forbid_lookup = forbid_lookup
        self.lookups: list[str] = []

    def source_url(self, **params: object) -> str:
        return "https://api.giftwiki.tg/gifts/monochromes?" + "&".join(f"{k}={v}" for k, v in params.items())

    async def iter_all_pages(self, max_pages: int) -> AsyncIterator[tuple[int, list[MonochromeRecord]]]:
        if self.fail:
            raise GiftWikiError("Gift Wiki unavailable")
        for page in range(1, max_pages + 1):
            chunk = self.records[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
            yield page, chunk
            if len(chunk) < PAGE_SIZE:
                return

    async def monochromes_for_gift(
        self, *, gift_name: str | None = None, gift_id: str | None = None, types: Iterable[str] | None = None
    ) -> list[MonochromeRecord]:
        if self.forbid_lookup:
            raise GiftWikiForbiddenError("Bearer app users cannot use gift_id/gift_name lookup filters")
        self.lookups.append(str(gift_name))
        return [r for r in self.records if r.gift_name == gift_name]


def make_sync(env: Env, client: FakeGiftWiki) -> GiftWikiSync:
    return GiftWikiSync(env.settings, client, env.sessionmaker, env.redis, env.store, env.enricher)  # type: ignore[arg-type]


async def test_sync_stores_records_with_provenance_and_enables_classification(env: Env) -> None:
    records = [rec(i, "Plush Pepe", f"Model{i}", "Black") for i in range(25)] + [
        rec(0, "Lunar Snake", "Albino", "White")
    ]
    client = FakeGiftWiki(records)
    report = await make_sync(env, client).run(trigger="test")
    assert report.status == "success"
    assert report.pages == 2 and report.records == 26 and report.added == 26
    assert set(client.lookups) == {"Plush Pepe", "Lunar Snake"}
    async with env.sessionmaker() as session:
        row = (
            await session.execute(
                select(GiftWikiMonochrome).where(GiftWikiMonochrome.record_id == "Plush Pepe-3")
            )
        ).scalar_one()
        attrs = (await session.execute(select(GiftWikiAttribute))).scalars().all()
        run = (await session.execute(select(GiftWikiSyncRun))).scalar_one()
    assert row.source_url and "gift_name=Plush Pepe" in row.source_url
    assert row.raw["x"] == 1 and row.fetched_at is not None and row.last_seen_at is not None
    assert {a.kind for a in attrs} == {"model", "backdrop"}
    assert run.status == "success" and run.finished_at is not None
    snap = env.store.snapshot
    assert snap.records_count == 26 and snap.last_success_at is not None
    assert env.enricher.classify(make_listing(model_name="Model3", backdrop_name="Black")).status is (
        MonochromeStatus.MONOCHROME
    )
    assert env.enricher.classify(make_listing(model_name="Model3", backdrop_name="Gray")).status is (
        MonochromeStatus.NOT_MONOCHROME
    )


async def test_removed_records_are_soft_deleted_and_reclassified(env: Env) -> None:
    records = [rec(0, "Plush Pepe", "Onyx", "Black"), rec(1, "Plush Pepe", "Ivory", "White")]
    await make_sync(env, FakeGiftWiki(records)).run()
    listing = make_listing("g-active", model_name="Onyx", backdrop_name="Black")
    async with env.sessionmaker() as session, session.begin():
        await listings_repo.upsert_gift(session, listing)
        await listings_repo.apply_event(
            session,
            "listing",
            listing,
            price_nano=listing.price_nano,
            event_date=None,
            source="feed",
            source_event_id="x",
            monochrome_status=env.enricher.classify(listing).status,
        )
    report = await make_sync(env, FakeGiftWiki(records[1:])).run()
    assert report.removed == 1
    async with env.sessionmaker() as session:
        removed = await session.get(GiftWikiMonochrome, "Plush Pepe-0")
        gift = await listings_repo.get_gift_row(session, "g-active")
    assert removed is not None and removed.removed_at is not None
    assert env.enricher.classify(listing).status is MonochromeStatus.NOT_MONOCHROME
    assert gift is not None and gift.monochrome_status == "NOT_MONOCHROME"  # active listings re-classified


async def test_failed_sync_keeps_previous_data(env: Env) -> None:
    await make_sync(env, FakeGiftWiki([rec(0, "Plush Pepe", "Onyx", "Black")])).run()
    before = env.store.snapshot.last_success_at
    report = await make_sync(env, FakeGiftWiki([], fail=True)).run()
    assert report.status == "failed" and "unavailable" in (report.error or "")
    await env.store.reload()
    assert env.store.snapshot.records_count == 1
    assert (
        env.store.snapshot.last_success_at == before
    )  # the age keeps growing, data is not presented as fresh
    assert env.enricher.classify(make_listing()).status is MonochromeStatus.MONOCHROME


async def test_forbidden_lookups_fall_back_to_complete_pagination(env: Env) -> None:
    report = await make_sync(
        env, FakeGiftWiki([rec(0, "Plush Pepe", "Onyx", "Black")], forbid_lookup=True)
    ).run()
    assert report.status == "partial" and report.lookups_failed == 1
    assert env.store.snapshot.gifts["id-Plush Pepe"].complete  # the full list came from pagination
    assert env.enricher.classify(make_listing(backdrop_name="Gray")).status is MonochromeStatus.NOT_MONOCHROME


async def test_gift_missing_from_complete_list_loses_records(env: Env) -> None:
    await make_sync(
        env, FakeGiftWiki([rec(0, "Plush Pepe", "Onyx", "Black"), rec(0, "Lunar Snake", "A", "B")])
    ).run()
    await make_sync(env, FakeGiftWiki([rec(0, "Lunar Snake", "A", "B")])).run()
    snap = env.store.snapshot
    assert snap.gifts["id-Plush Pepe"].records_count == 0
    # zero records => cannot tell "no monochromes" from "not catalogued" => UNKNOWN, never a guess
    assert env.enricher.classify(make_listing()).status is MonochromeStatus.UNKNOWN


async def test_sync_without_api_key_is_skipped(env: Env) -> None:
    client = FakeGiftWiki([])
    client.configured = False  # type: ignore[misc]
    report = await make_sync(env, client).run()
    assert report.status == "skipped" and "GIFTWIKI_API_KEY" in (report.error or "")


async def test_data_age_is_reported(env: Env) -> None:
    await make_sync(env, FakeGiftWiki([rec(0, "Plush Pepe", "Onyx", "Black")])).run()
    enrichment = await env.enricher.enrich(make_listing())
    assert enrichment.giftwiki_data_age_hours is not None and enrichment.giftwiki_data_age_hours < 0.1
    assert enrichment.model_drop_probability is None  # not published by the documented API
    assert env.store.snapshot.age_hours(datetime.now(UTC)) is not None


async def test_sync_stores_mapping_table(env: Env) -> None:
    from gift_sniper.db.models import CollectionMapping

    async with env.sessionmaker() as session, session.begin():
        await listings_repo.upsert_collections(
            session, [("Plush Pepe", "Plush Pepe", None), ("Lunar Snake", "Lunar Snake", None)]
        )
    await make_sync(env, FakeGiftWiki([rec(0, "Plush Pepe", "Onyx", "Black")])).run()
    async with env.sessionmaker() as session:
        rows = {
            m.mrkt_collection_name: m for m in (await session.execute(select(CollectionMapping))).scalars()
        }
    assert rows["Plush Pepe"].status == "matched" and rows["Plush Pepe"].giftwiki_gift_id == "id-Plush Pepe"
    assert rows["Lunar Snake"].status == "not_found" and rows["Lunar Snake"].giftwiki_gift_id is None
