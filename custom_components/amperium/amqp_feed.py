"""Live power straight from Amperium's own feed, like the app's live power view.

What this is based on: the Android app (2.3.0) opens a transient subscription with
``POST /api/sites/{id}/stream/amqp`` and then consumes the queue named in the answer
over RabbitMQ (AMQP). Messages have the routing key ``<MID>.O.<observation id>``
(101 = active power import, 102 = export) and a JSON body with a timestamp and a
value in watts. This was read from the app's code; it has not yet been confirmed
against a live feed from a real meter, so the feed reports its own state
(``LiveFeedState.status``) to make that easy to check.

The module itself needs no Home Assistant. The AMQP client (aio-pika) is imported only
when the feed runs, and is installed on first use (see ``async_prepare_library``).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import hashlib
import importlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .api import AmperiumClient, LiveSubscription, _parse_dt
from .const import (
    DOMAIN,
    LIVE_DOWN_AFTER_SECONDS,
    LIVE_FEED_TTL_SECONDS,
    LIVE_MAX_AGE_SECONDS,
    LIVE_OBS_IMPORT,
    LIVE_REQUIREMENTS,
)

_LOGGER = logging.getLogger(__name__)

# Waits between attempts after a failure; the last one repeats. A new subscription is asked
# for before every attempt (never reused), so a long wait only spares Amperium while it is down.
BACKOFF_SECONDS = (5, 15, 30, 60, 120, 300, 600)
# A stream that ends or goes quiet is not an error (the meter may just be silent). The wait
# after that never grows past this, so live power is back within 5 minutes of the meter.
QUIET_BACKOFF_CAP_SECONDS = 300
# Subscribe again when nothing has arrived for this long (the queue may have expired).
# The meter sends about every 2 s, so a minute of silence means the feed has stopped.
IDLE_RESUBSCRIBE_SECONDS = 60
# Take a new subscription before the old one expires. The subscription is asked for with
# a lifetime of 300 s (LIVE_FEED_TTL_SECONDS); a real feed was seen to stop after about
# 10 minutes without any error, so renew well inside the lifetime.
RENEW_AFTER_SECONDS = 240
# The short pause between a planned renewal and the next subscription.
RENEW_PAUSE_SECONDS = 1
# How often listeners are told to re-read the state (so an old reading goes stale).
TICK_SECONDS = 30
# How often the listening checks whether it is time to renew or the feed went quiet.
CHECK_SECONDS = 10
# How often the listening checks that the broker has not cancelled its consumer (see
# ``consume_with_aio_pika``).
CONSUMER_CHECK_SECONDS = 2.0

# Every value LiveFeedState.status can have.
LIVE_STATUSES = ("off", "starting", "connecting", "connected", "error", "unavailable")

Listener = Callable[[], None]


def parse_routing_key(key: Any) -> tuple[str, int] | None:
    """Return (MID, observation id) for ``<MID>.O.<id>``, else None."""
    if not isinstance(key, str):
        return None
    parts = key.split(".")
    if len(parts) > 2 and parts[1] == "O" and parts[2].isdigit():
        return parts[0], int(parts[2])
    return None


def parse_observation(body: Any) -> tuple[dt.datetime | None, float | None]:
    """Read (timestamp, value) from a JSON observation. Value is returned as sent.

    Accepts a single object or a list (the last item counts) and both
    ``Timestamp``/``Value`` and the short ``t``/``v`` spellings, in any case.
    """
    try:
        text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
        data = json.loads(text)
    except (ValueError, UnicodeDecodeError):
        return None, None
    if isinstance(data, list):
        data = data[-1] if data else None
    if not isinstance(data, dict):
        return None, None
    fields = {str(k).lower(): v for k, v in data.items()}
    raw = fields.get("value", fields.get("v"))
    try:
        value = None if raw is None or isinstance(raw, bool) else float(raw)
    except (TypeError, ValueError):
        value = None
    return _parse_dt(fields.get("timestamp", fields.get("t"))), value


class LiveFeedState:
    """What the feed knows right now; entities read it and listen for changes."""

    def __init__(self) -> None:
        """Start with the feed switched off and nothing received."""
        self.status = "off"
        self.messages = 0
        self.import_kw: float | None = None
        self.import_observed: dt.datetime | None = None
        self.last_error: str | None = None  # the current problem; None while it works
        self.last_error_at: dt.datetime | None = None  # when the latest error happened
        self.failures = 0  # attempts in a row that failed (0 while it works)
        self.started_at: dt.datetime | None = None  # when the feed was started
        self.last_message_at: dt.datetime | None = None  # when the latest reading arrived
        self._fresh_at: dt.datetime | None = None
        self._listeners: list[Listener] = []

    def add_listener(self, listener: Listener) -> Callable[[], None]:
        """Call ``listener`` on every change; returns a function that removes it."""
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def notify(self) -> None:
        """Tell listeners to re-read the state."""
        for listener in list(self._listeners):
            listener()

    def set_status(self, status: str) -> None:
        """Change the status (and tell listeners if it changed)."""
        if status != self.status:
            self.status = status
            self.notify()

    def set_import(
        self,
        kw: float,
        observed: dt.datetime | None,
        fresh_at: dt.datetime,
    ) -> None:
        """Store a reading. ``fresh_at`` is what its age is counted from."""
        self.import_kw = kw
        self.import_observed = observed
        self._fresh_at = fresh_at
        self.notify()

    def age_seconds(self, now: dt.datetime) -> float | None:
        """Seconds since the last reading counts as fresh (None if none yet)."""
        if self._fresh_at is None:
            return None
        return max(0.0, (now - self._fresh_at).total_seconds())

    def current_kw(self, now: dt.datetime, max_age: float = LIVE_MAX_AGE_SECONDS) -> float | None:
        """The import power in kW, or None when there is no recent reading."""
        age = self.age_seconds(now)
        if self.import_kw is None or age is None or age > max_age:
            return None
        return self.import_kw

    def silent_seconds(self, now: dt.datetime) -> float | None:
        """Seconds since the latest reading arrived (since the start if none has).

        None before the feed has been started.
        """
        since = self.last_message_at or self.started_at
        if since is None:
            return None
        return max(0.0, (now - since).total_seconds())

    def is_down(self, now: dt.datetime, limit: float = LIVE_DOWN_AFTER_SECONDS) -> bool:
        """True when nothing has arrived for longer than ``limit`` seconds.

        It does not matter why: the stream may be failing, or it may be up while the
        meter sends nothing. Either way there is no live power to show.
        """
        silent = self.silent_seconds(now)
        return silent is not None and silent > limit


def _safe_error(err: BaseException, secrets: list[Any]) -> str:
    """An error text that cannot contain credentials, hosts or queue names."""
    message = str(err).strip()
    text = f"{type(err).__name__}: {message}" if message else f"{type(err).__name__} (no details)"
    text = re.sub(r"amqps?://\S+", "<url>", text)
    for secret in secrets:
        if isinstance(secret, str) and len(secret) >= 3:
            text = text.replace(secret, "***")
    return text[:300]


ConsumeFn = Callable[[dict[str, Any], Callable[[str, bytes], None]], Awaitable[None]]

_SAME_DETAILS = " (same connection details as the attempt before)"
RECONNECT_REQUESTED = "reconnect requested"


def _fingerprint(details: dict[str, Any]) -> str:
    """A hash of who and where the subscription logs in, to tell if two answers are identical.

    Only compared with another hash; it is never logged or shown.
    """
    text = "|".join(str(details.get(key)) for key in ("server", "username", "queueName"))
    return hashlib.sha256(text.encode()).hexdigest()


class AmperiumLiveFeed:
    """Keeps a live subscription going and stores the latest import power."""

    def __init__(
        self,
        client: AmperiumClient,
        site_id: int,
        *,
        state: LiveFeedState | None = None,
        consume: ConsumeFn | None = None,
        ensure_library: Callable[[], Awaitable[bool]] | None = None,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        """Set up the feed; ``consume`` and ``ensure_library`` can be replaced in tests."""
        self._client = client
        self._site_id = site_id
        self.state = state or LiveFeedState()
        self._consume = consume or consume_with_aio_pika
        self._ensure_library = ensure_library or _library_already_installed
        self._sleep = sleep
        self._last_message = time.monotonic()
        self._first_message_logged = False
        self._wake = asyncio.Event()  # set by request_reconnect()
        self._failures = 0
        # The problem the log last told about (None while the feed works); a repeat of it
        # is not logged again, so an outage of hours is one warning and one "working again".
        self._problem_logged: str | None = None
        self._problem_since: float | None = None
        self._failed_fingerprint: str | None = None

    @staticmethod
    def _now() -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)

    def handle_message(self, routing_key: str, body: bytes) -> None:
        """Take one message from the queue."""
        parsed = parse_routing_key(routing_key)
        if parsed is None or parsed[1] != LIVE_OBS_IMPORT:
            return
        observed, watts = parse_observation(body)
        if watts is None:
            _LOGGER.debug("Amperium live feed: could not read a value from a message")
            return
        self._last_message = time.monotonic()
        self.state.messages += 1
        self.state.last_message_at = self._now()
        self.state.failures = 0
        self._failed_fingerprint = None
        if self.state.last_error is not None:
            self.state.last_error = None  # readings arrive again, so the problem is over
        if self._problem_logged is not None:
            minutes = (time.monotonic() - (self._problem_since or time.monotonic())) / 60
            _LOGGER.info("Amperium live feed: working again after %.0f min", minutes)
            self._problem_logged = None
            self._problem_since = None
        if not self._first_message_logged:
            self._first_message_logged = True
            _LOGGER.info("Amperium live feed: first power reading received")
        self.state.set_import(watts / 1000.0, observed, self._now())

    def _take_history(self, subscription: LiveSubscription) -> None:
        """Use the newest buffered reading from the subscription answer, if any."""
        if subscription.import_observations:
            observed, watts = subscription.import_observations[-1]
            self.state.set_import(watts / 1000.0, observed, observed)
            if self.state.last_message_at is None or observed > self.state.last_message_at:
                self.state.last_message_at = observed

    def request_reconnect(self) -> bool:
        """Drop the stream and subscribe again now, without waiting out a backoff.

        Returns False when the feed is not running (it was never started, or the
        library could not be installed), which a reconnect cannot fix.
        """
        if self.state.status in ("off", "unavailable"):
            return False
        self._failures = 0
        self.state.failures = 0
        self._wake.set()
        return True

    def _report_problem(self, text: str, *, hard: bool, delay: float) -> None:
        """Log a problem once. The same problem again is only logged at DEBUG.

        ``hard`` is an error (a warning); a stream that just ended or went quiet is not.
        """
        if text == self._problem_logged:
            _LOGGER.debug("Amperium live feed: %s (trying again in %s s)", text, delay)
            return
        self._problem_logged = text
        if self._problem_since is None:
            self._problem_since = time.monotonic()
        _LOGGER.log(
            logging.WARNING if hard else logging.INFO,
            "Amperium live feed: %s (trying again in %s s; the same problem is not logged "
            "again until it changes or goes away)",
            text,
            delay,
        )

    async def _pause(self, seconds: float) -> None:
        """Wait ``seconds``, or less if a reconnect is requested meanwhile."""
        if self._wake.is_set():
            return
        sleeper = asyncio.ensure_future(self._sleep(seconds))
        waker = asyncio.ensure_future(self._wake.wait())
        try:
            await asyncio.wait({sleeper, waker}, return_when=asyncio.FIRST_COMPLETED)
            if sleeper.done():
                sleeper.result()  # lets a cancellation or an error from the wait through
        finally:
            for task in (sleeper, waker):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sleeper, waker, return_exceptions=True)

    async def run(self) -> None:
        """Run until cancelled: subscribe, listen, and start over after any failure."""
        state = self.state
        state.started_at = self._now()
        state.set_status("starting")
        if not await self._ensure_library():
            state.set_status("unavailable")
            return
        ticker = asyncio.create_task(self._tick())
        try:
            while True:
                secrets: list[Any] = []
                fingerprint: str | None = None
                problem: tuple[str, bool] | None = None  # (text, is it an error)
                started = time.monotonic()
                messages_before = state.messages
                self._wake.clear()
                try:
                    state.set_status("connecting")
                    # Always a new subscription: the details of an earlier one may have expired.
                    subscription = await self._client.async_create_live_subscription(
                        self._site_id, ttl_seconds=LIVE_FEED_TTL_SECONDS
                    )
                    secrets = list(subscription.details.values())
                    fingerprint = _fingerprint(subscription.details)
                    self._take_history(subscription)
                    self._first_message_logged = False
                    self._last_message = time.monotonic()
                    state.set_status("connected")
                    reason = await self._listen(subscription.details)
                    if reason == "renew":
                        _LOGGER.debug("Amperium live feed: renewing the subscription")
                        self._failures = 0
                        await self._pause(RENEW_PAUSE_SECONDS)
                        continue
                    if reason == RECONNECT_REQUESTED:
                        _LOGGER.info("Amperium live feed: reconnecting on request")
                        self._failures = 0
                        continue
                    problem = (reason, False)
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001 - any failure means "try again later"
                    text = _safe_error(err, secrets)
                    if fingerprint is not None and fingerprint == self._failed_fingerprint:
                        text += _SAME_DETAILS
                    if fingerprint is not None:
                        self._failed_fingerprint = fingerprint
                    state.last_error = text
                    state.last_error_at = self._now()
                    state.set_status("error")
                    problem = (text, True)
                if state.messages > messages_before and time.monotonic() - started > 60:
                    self._failures = 0  # it worked for a while; start again from the short wait
                    delay = BACKOFF_SECONDS[0]
                else:
                    delay = BACKOFF_SECONDS[min(self._failures, len(BACKOFF_SECONDS) - 1)]
                    self._failures += 1
                state.failures = self._failures
                if problem is not None and not problem[1]:
                    delay = min(delay, QUIET_BACKOFF_CAP_SECONDS)
                if problem is not None:
                    self._report_problem(problem[0], hard=problem[1], delay=delay)
                await self._pause(delay)
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker
            state.set_status("off")

    async def _listen(self, details: dict[str, Any]) -> str:
        """Consume the queue; say why it stopped.

        Returns "renew" (time for a new subscription), "reconnect requested",
        "nothing received for N s" (the feed went quiet) or "connection ended".
        Errors are raised.
        """
        task = asyncio.ensure_future(self._consume(details, self.handle_message))
        waker = asyncio.ensure_future(self._wake.wait())
        started = time.monotonic()
        check = min(CHECK_SECONDS, IDLE_RESUBSCRIBE_SECONDS, RENEW_AFTER_SECONDS)
        try:
            while not task.done():
                await asyncio.wait({task, waker}, timeout=check, return_when=asyncio.FIRST_COMPLETED)
                if task.done():
                    break
                if self._wake.is_set():
                    return RECONNECT_REQUESTED
                now = time.monotonic()
                if now - started >= RENEW_AFTER_SECONDS:
                    return "renew"
                if now - self._last_message > IDLE_RESUBSCRIBE_SECONDS:
                    return f"nothing received for {IDLE_RESUBSCRIBE_SECONDS} s"
            task.result()
            return "connection ended"
        finally:
            waker.cancel()
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await waker

    async def _tick(self) -> None:
        """Wake the listeners now and then so an old reading is shown as gone."""
        while True:
            await asyncio.sleep(TICK_SECONDS)
            self.state.notify()


async def _library_already_installed() -> bool:
    """Default check: is aio-pika importable?"""
    try:
        importlib.import_module("aio_pika")
    except ImportError:
        return False
    return True


async def async_prepare_library(hass: Any) -> bool:
    """Make sure aio-pika is available, installing it the first time it is needed.

    Returns False (and logs why) instead of raising, so a failed install only
    switches the live feed off and never affects the rest of the integration.
    """
    try:
        await hass.async_add_executor_job(importlib.import_module, "aio_pika")
        return True
    except ImportError:
        pass
    try:
        from homeassistant.requirements import async_process_requirements

        await async_process_requirements(hass, DOMAIN, LIVE_REQUIREMENTS)
        importlib.invalidate_caches()
        await hass.async_add_executor_job(importlib.import_module, "aio_pika")
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Amperium live feed is off: could not install %s (%s)",
            ", ".join(LIVE_REQUIREMENTS),
            type(err).__name__,
        )
        return False


async def consume_with_aio_pika(
    details: dict[str, Any],
    on_message: Callable[[str, bytes], None],
    ssl_context: Any = None,
) -> None:
    """Connect to Amperium's RabbitMQ and pass every message to ``on_message``.

    Like the app: connect with the details from the subscription, then consume the
    queue directly (nothing is declared or bound). Returns when the connection or
    channel closes.
    """
    import aio_pika

    use_ssl = bool(details.get("useSsl"))
    connection = await aio_pika.connect(
        host=details["server"],
        port=int(details.get("port") or (5671 if use_ssl else 5672)),
        login=details.get("username") or "guest",
        password=details.get("password") or "guest",
        virtualhost=details.get("virtualHost") or "/",
        ssl=use_ssl,
        ssl_context=ssl_context if use_ssl else None,
        timeout=20,
    )
    closed = asyncio.Event()
    connection.close_callbacks.add(lambda *_: closed.set())
    try:
        channel = await connection.channel()
        channel.close_callbacks.add(lambda *_: closed.set())
        # The broker cancels the consumer when the queue is removed (for example when
        # the subscription expires). The connection and channel then stay open without
        # any error, so this must end the listening too.
        inner = getattr(channel, "channel", None)  # the aiormq channel under aio-pika's
        cancel_callbacks = getattr(inner, "on_consumer_cancel_callbacks", None)
        if cancel_callbacks is not None:  # aiormq 7 (aio-pika 10)
            cancel_callbacks.add(lambda *_: closed.set())
        await channel.set_qos(prefetch_count=20)
        queue = await channel.get_queue(details["queueName"], ensure=False)

        async def handler(message: Any) -> None:
            on_message(message.routing_key or "", message.body)

        consumer_tag = await queue.consume(handler, no_ack=True)
        # aiormq 6 (aio-pika 9) has no cancel callback: on a cancel from the broker it only
        # drops the consumer from ``channel.consumers``, so that is checked now and then too.
        # Without it the listening stayed on until the feed's silence limit (tested against a
        # real RabbitMQ, tests/test_real_rabbitmq.py).
        while True:
            try:
                await asyncio.wait_for(closed.wait(), timeout=CONSUMER_CHECK_SECONDS)
                break
            except TimeoutError:
                consumers = getattr(inner, "consumers", None)
                if consumers is not None and consumer_tag not in consumers:
                    break
    finally:
        with contextlib.suppress(Exception):
            await connection.close()
