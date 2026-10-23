"""Prometheus metrics and the /health + /metrics HTTP endpoint."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

log = logging.getLogger(__name__)

LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 30, 60, 120)
FAST_BUCKETS = (0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1)

DETECTION_LATENCY = Histogram(
    "sniper_listing_detection_latency_seconds",
    "Time between the MRKT event timestamp and its detection by the monitor",
    buckets=LATENCY_BUCKETS,
)
FILTER_PROCESSING = Histogram(
    "sniper_filter_processing_seconds",
    "Time to enrich a listing and evaluate all active filters",
    buckets=FAST_BUCKETS,
)
EVENT_TO_DECISION = Histogram(
    "sniper_event_to_purchase_decision_seconds",
    "Time from detection to the purchase decision (enqueue)",
    buckets=FAST_BUCKETS,
)
EXTERNAL_REQUESTS = Counter(
    "sniper_external_requests_total", "Requests to external APIs", ["service", "endpoint", "outcome"]
)
EXTERNAL_LATENCY = Histogram(
    "sniper_external_request_seconds",
    "External API latency",
    ["service", "endpoint"],
    buckets=LATENCY_BUCKETS,
)
EVENTS_SEEN = Counter("sniper_feed_events_total", "MRKT feed events by type", ["type", "is_new"])
PURCHASES = Counter(
    "sniper_purchase_attempts_total", "Purchase attempts by final status", ["run_mode", "status"]
)
NOTIFICATIONS = Counter(
    "sniper_notifications_total", "Notifications by kind and outcome", ["kind", "outcome"]
)
GIFTWIKI_LAST_SUCCESS = Gauge(
    "sniper_giftwiki_last_success_timestamp", "Unix time of the last successful sync"
)
GIFTWIKI_RECORDS = Gauge("sniper_giftwiki_monochrome_records", "Monochrome records currently stored")
MONITOR_LAST_POLL = Gauge("sniper_monitor_last_poll_timestamp", "Unix time of the last successful MRKT poll")
QUEUE_BACKLOG = Gauge("sniper_queue_backlog", "Pending messages in Redis streams", ["stream"])
KILL_SWITCH = Gauge("sniper_kill_switch", "1 when all automatic purchases are stopped")


class Timer:
    def __init__(self) -> None:
        self.start = time.perf_counter()

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.start


HealthProbe = Callable[[], Awaitable[dict[str, Any]]]


async def start_http_server(host: str, port: int, health_probe: HealthProbe) -> web.AppRunner:
    async def metrics(_: web.Request) -> web.Response:
        return web.Response(body=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    async def health(_: web.Request) -> web.Response:
        try:
            details = await health_probe()
        except Exception as exc:  # health endpoint must never crash
            log.exception("health probe failed")
            return web.json_response({"status": "error", "error": str(exc)}, status=503)
        status = 200 if details.get("status") == "ok" else 503
        return web.json_response(details, status=status)

    app = web.Application()
    app.router.add_get("/metrics", metrics)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("metrics server started", extra={"host": host, "port": port})
    return runner
