"""Tests for Amperium's live feed (state, loop, backoff, reconnect, aio-pika glue)."""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from conftest import amqp_feed, api, const
from helpers import (
    DETAILS,
    UTC,
    _sub,
)


# --- live feed: routing keys and messages (as read from the app's code) -----------------
@pytest.mark.parametrize("key,expected", [
    ("AMPMETER-ABC123.O.101", ("AMPMETER-ABC123", 101)),
    ("MID.O.102", ("MID", 102)),
    ("MID.O.101.extra", ("MID", 101)),
    ("MID.P", None),           # pulse
    ("MID.C.5", None),         # command
    ("MID.O.x", None),         # id is not a number
    ("MID", None),
    ("", None),
    (None, None),
    (101, None),
])
def test_routing_key(key, expected):
    assert amqp_feed.parse_routing_key(key) == expected


def test_observation_json_variants():
    when = dt.datetime(2026, 10, 3, 19, 0, 5, tzinfo=UTC)
    assert amqp_feed.parse_observation(b'{"Timestamp":"2026-10-03T19:00:05Z","Value":1351.0}') == (when, 1351.0)
    assert amqp_feed.parse_observation(b'{"timestamp":"2026-10-03T19:00:05Z","value":1351}') == (when, 1351.0)
    assert amqp_feed.parse_observation(b'{"t":"2026-10-03T19:00:05Z","v":"1351.5"}') == (when, 1351.5)
    assert amqp_feed.parse_observation(b'[{"v":1},{"v":2}]')[1] == 2.0  # last item of a list
    assert amqp_feed.parse_observation(b'{"Value": 0}')[1] == 0.0  # zero is a value


@pytest.mark.parametrize("body", [b"", b"not json", b"{}", b"[]", b'{"Value": null}',
                                  b'{"Value": "abc"}', b'{"Value": true}', b"\xff\xfe", b"42"])
def test_observation_garbage_gives_no_value(body):
    assert amqp_feed.parse_observation(body)[1] is None


# --- live feed: state ---------------------------------------------------------------------
def test_state_reading_goes_stale():
    state = amqp_feed.LiveFeedState()
    t0 = dt.datetime(2026, 10, 3, 19, 0, tzinfo=UTC)
    assert state.current_kw(t0) is None
    state.set_import(1.35, None, t0)
    assert state.current_kw(t0 + dt.timedelta(seconds=119)) == 1.35
    assert state.current_kw(t0 + dt.timedelta(seconds=121)) is None  # older than 120 s
    assert state.age_seconds(t0 + dt.timedelta(seconds=10)) == 10


def test_state_zero_is_kept_not_treated_as_missing():
    state = amqp_feed.LiveFeedState()
    t0 = dt.datetime(2026, 10, 3, 19, 0, tzinfo=UTC)
    state.set_import(0.0, None, t0)
    assert state.current_kw(t0) == 0.0


def test_state_listeners_hear_changes_and_can_leave():
    state, heard = amqp_feed.LiveFeedState(), []
    remove = state.add_listener(lambda: heard.append(state.status))
    state.set_status("connecting")
    state.set_status("connecting")      # no change -> no call
    state.set_status("connected")
    remove()
    state.set_status("error")
    assert heard == ["connecting", "connected"]


# --- live feed: the loop, with a fake client and a fake queue -----------------------------
class _FakeClient:
    """Hands out scripted subscriptions (or errors) like async_create_live_subscription."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def async_create_live_subscription(self, site_id, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _run_feed(client, consume, *, library=True, stop_after_sleeps=1):
    """Run the feed until it has slept ``stop_after_sleeps`` times; return (feed, sleeps)."""
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= stop_after_sleeps:
            raise asyncio.CancelledError

    async def ensure():
        return library

    feed = amqp_feed.AmperiumLiveFeed(client, 7001, consume=consume, ensure_library=ensure, sleep=sleep)

    async def go():
        try:
            await feed.run()
        except asyncio.CancelledError:
            pass

    async def guarded():
        task = asyncio.ensure_future(go())
        done, _ = await asyncio.wait({task}, timeout=10)
        assert done, "the feed never reached the expected point (it hung)"

    asyncio.run(guarded())
    return feed, sleeps


def test_feed_stores_power_in_kw_from_messages():
    async def consume(details, on_message):
        on_message("AMPMETER-X.O.101", b'{"Timestamp":"2026-10-03T19:00:05Z","Value":1351}')
        on_message("AMPMETER-X.O.102", b'{"Value":999}')       # export: ignored
        on_message("AMPMETER-X.O.101", b'{"Value":1349.5}')

    feed, _ = _run_feed(_FakeClient([_sub()]), consume)
    assert feed.state.import_kw == pytest.approx(1.3495)
    assert feed.state.messages == 2


def test_feed_uses_newest_buffered_reading_from_the_subscription():
    old = (dt.datetime.now(UTC) - dt.timedelta(seconds=30), 1000.0)
    new = (dt.datetime.now(UTC) - dt.timedelta(seconds=5), 2500.0)

    async def consume(details, on_message):
        return None

    feed, _ = _run_feed(_FakeClient([_sub([old, new])]), consume)
    assert feed.state.import_kw == pytest.approx(2.5)


def test_feed_without_the_library_stays_off_and_never_subscribes():
    client = _FakeClient([])
    feed, sleeps = _run_feed(client, lambda *a: None, library=False)
    assert feed.state.status == "unavailable"
    assert client.calls == 0 and sleeps == []


def test_feed_backs_off_after_errors_and_gives_the_error_without_secrets(caplog):
    client = _FakeClient([api.AmperiumError("HTTP 503"), api.AmperiumError("HTTP 503")])

    async def consume(details, on_message):
        raise AssertionError("never reached")

    state, seen = amqp_feed.LiveFeedState(), []
    state.add_listener(lambda: seen.append(state.status))
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            raise asyncio.CancelledError

    async def ensure():
        return True

    feed = amqp_feed.AmperiumLiveFeed(client, 7001, state=state, consume=consume,
                                      ensure_library=ensure, sleep=sleep)

    async def go():
        try:
            await feed.run()
        except asyncio.CancelledError:
            pass

    with caplog.at_level("WARNING"):
        asyncio.run(go())
    assert sleeps == [5, 15]
    assert seen[:3] == ["starting", "connecting", "error"]  # went to "error" while failing
    assert seen[-1] == "off"                                 # and "off" once stopped
    assert "HTTP 503" in state.last_error


def test_feed_errors_from_the_connection_never_show_credentials(caplog):
    client = _FakeClient([_sub()])

    async def consume(details, on_message):
        raise ConnectionError(
            "failed amqps://user-secret:pw-secret@mq.example.test:5671/vh queue-secret exchange-secret"
        )

    with caplog.at_level("DEBUG"):
        feed, _ = _run_feed(client, consume)
    shown = feed.state.last_error + caplog.text
    for secret in ("user-secret", "pw-secret", "mq.example.test", "queue-secret", "exchange-secret"):
        assert secret not in shown
    assert "ConnectionError" in feed.state.last_error


def test_feed_subscribes_again_when_the_connection_ends():
    client = _FakeClient([_sub(), _sub()])
    calls = []

    async def consume(details, on_message):
        calls.append(1)

    _feed, sleeps = _run_feed(client, consume, stop_after_sleeps=2)
    assert client.calls == 2 and len(calls) == 2
    assert sleeps == [5, 15]  # no message arrived, so it counts as a failed session


def test_feed_resubscribes_when_nothing_arrives_for_too_long(monkeypatch):
    monkeypatch.setattr(amqp_feed, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(amqp_feed, "IDLE_RESUBSCRIBE_SECONDS", 0.03)
    client = _FakeClient([_sub()])
    cancelled = []

    async def consume(details, on_message):
        try:
            await asyncio.sleep(30)  # a quiet queue
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    feed, sleeps = _run_feed(client, consume)
    assert cancelled == [True]  # the idle listener was dropped
    assert sleeps == [5]
    assert feed.state.messages == 0


# --- the aio-pika glue, with a fake library (checks how we call it, not RabbitMQ itself) -----
class _FakeCallbacks:
    def __init__(self):
        self.callbacks = []

    def add(self, callback, weak=False):
        self.callbacks.append(callback)

    def fire(self):
        for callback in self.callbacks:
            callback(None, None)


class _FakeMessage:
    def __init__(self, routing_key, body):
        self.routing_key, self.body = routing_key, body


class _FakeQueue:
    def __init__(self, channel):
        self.channel = channel

    async def consume(self, handler, no_ack=False, **kwargs):
        self.channel.consumed = {"handler": handler, "no_ack": no_ack}
        consumers = getattr(getattr(self.channel, "channel", None), "consumers", None)
        if consumers is not None:
            consumers["ctag-1"] = handler          # as aiormq does
        return "ctag-1"


class _FakeChannel:
    def __init__(self):
        import types
        self.close_callbacks = _FakeCallbacks()
        # the underlying aiormq channel, which tells us when the broker cancels a consumer
        self.channel = types.SimpleNamespace(on_consumer_cancel_callbacks=set(), consumers={})
        self.qos = None
        self.queue_asked = None
        self.consumed = None

    async def set_qos(self, prefetch_count=0, **kwargs):
        self.qos = prefetch_count

    async def get_queue(self, name, *, ensure=True):
        self.queue_asked = (name, ensure)
        return _FakeQueue(self)


class _FakeConnection:
    def __init__(self):
        self.close_callbacks = _FakeCallbacks()
        self.channel_obj = _FakeChannel()
        self.closed = False

    async def channel(self):
        return self.channel_obj

    async def close(self):
        self.closed = True


def test_aio_pika_glue_connects_like_the_app_and_passes_messages_on(monkeypatch):
    import sys
    import types

    connection = _FakeConnection()
    seen = {}

    async def fake_connect(**kwargs):
        seen.update(kwargs)
        return connection

    monkeypatch.setitem(sys.modules, "aio_pika", types.SimpleNamespace(connect=fake_connect))
    got = []
    ssl_context = object()

    async def go():
        task = asyncio.ensure_future(amqp_feed.consume_with_aio_pika(
            dict(DETAILS), lambda key, body: got.append((key, body)), ssl_context=ssl_context))
        for _ in range(5):          # let it connect and start consuming
            await asyncio.sleep(0)
        consumed = connection.channel_obj.consumed
        await consumed["handler"](_FakeMessage("AMPMETER-X.O.101", b'{"Value": 5}'))
        assert not task.done()      # keeps listening until the connection closes
        connection.close_callbacks.fire()
        await asyncio.wait_for(task, 1)

    asyncio.run(go())
    assert (seen["host"], seen["port"], seen["virtualhost"]) == ("mq.example.test", 5671, "vh")
    assert (seen["login"], seen["password"], seen["ssl"]) == ("u", "p", True)
    assert seen["ssl_context"] is ssl_context
    assert connection.channel_obj.queue_asked == ("q", False)   # not declared, like the app
    assert connection.channel_obj.consumed["no_ack"] is True
    assert got == [("AMPMETER-X.O.101", b'{"Value": 5}')]
    assert connection.closed is True


def test_aio_pika_glue_without_tls_uses_the_plain_port_and_no_context(monkeypatch):
    import sys
    import types

    connection, seen = _FakeConnection(), {}

    async def fake_connect(**kwargs):
        seen.update(kwargs)
        return connection

    monkeypatch.setitem(sys.modules, "aio_pika", types.SimpleNamespace(connect=fake_connect))
    details = {"server": "s", "useSsl": False, "queueName": "q", "username": "u", "password": "p"}

    async def go():
        task = asyncio.ensure_future(amqp_feed.consume_with_aio_pika(details, lambda *a: None,
                                                                      ssl_context=object()))
        for _ in range(5):
            await asyncio.sleep(0)
        connection.channel_obj.close_callbacks.fire()   # the channel closing also ends it
        await asyncio.wait_for(task, 1)

    asyncio.run(go())
    assert seen["port"] == 5672 and seen["ssl"] is False and seen["ssl_context"] is None
    assert seen["virtualhost"] == "/"


# --- the feed stopped after ~10 minutes with no error (real HA, 3 October 2026) --------------
def test_timings_renew_inside_the_lifetime_and_notice_silence_before_the_sensor_goes_unknown():
    assert amqp_feed.RENEW_AFTER_SECONDS < const.LIVE_FEED_TTL_SECONDS
    assert amqp_feed.IDLE_RESUBSCRIBE_SECONDS < const.LIVE_MAX_AGE_SECONDS
    assert amqp_feed.CHECK_SECONDS <= 10


def test_feed_renews_the_subscription_before_it_expires(monkeypatch):
    monkeypatch.setattr(amqp_feed, "CHECK_SECONDS", 0.01)
    monkeypatch.setattr(amqp_feed, "RENEW_AFTER_SECONDS", 0.05)
    monkeypatch.setattr(amqp_feed, "IDLE_RESUBSCRIBE_SECONDS", 30)
    client = _FakeClient([_sub(), _sub()])
    cancelled = []

    async def consume(details, on_message):
        try:
            while True:                       # a feed that keeps delivering
                on_message("MID.O.101", b'{"Value": 1200}')
                await asyncio.sleep(0.005)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    feed, sleeps = _run_feed(client, consume, stop_after_sleeps=2)
    assert client.calls == 2                  # a second subscription was taken
    assert cancelled == [True, True]          # each old listener was dropped
    assert sleeps == [amqp_feed.RENEW_PAUSE_SECONDS, amqp_feed.RENEW_PAUSE_SECONDS]
    assert feed.state.import_kw == pytest.approx(1.2)


def test_a_renewal_resets_the_failure_count(monkeypatch):
    """After a run of failures, a good session that is renewed starts the waits over."""
    calls = {"n": 0}

    class Client(_FakeClient):
        async def async_create_live_subscription(self, site_id, **kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise api.AmperiumError("HTTP 503")
            return _sub()

    async def consume(details, on_message):
        on_message("MID.O.101", b'{"Value": 1000}')
        await asyncio.sleep(0.03)

    monkeypatch.setattr(amqp_feed, "CHECK_SECONDS", 0.01)
    monkeypatch.setattr(amqp_feed, "RENEW_AFTER_SECONDS", 0.02)
    _feed, sleeps = _run_feed(Client([]), consume, stop_after_sleeps=4)
    assert sleeps == [5, 15, amqp_feed.RENEW_PAUSE_SECONDS, amqp_feed.RENEW_PAUSE_SECONDS]


def test_feed_resubscribes_after_a_minute_of_silence_by_default():
    assert amqp_feed.IDLE_RESUBSCRIBE_SECONDS == 60


def test_aio_pika_glue_ends_when_the_broker_cancels_the_consumer(monkeypatch):
    """The queue expired: connection and channel stay open, but the consumer is cancelled."""
    import sys
    import types

    connection = _FakeConnection()

    async def fake_connect(**kwargs):
        return connection

    monkeypatch.setitem(sys.modules, "aio_pika", types.SimpleNamespace(connect=fake_connect))

    async def go():
        task = asyncio.ensure_future(amqp_feed.consume_with_aio_pika(dict(DETAILS), lambda *a: None))
        for _ in range(5):
            await asyncio.sleep(0)
        assert not task.done()
        for callback in list(connection.channel_obj.channel.on_consumer_cancel_callbacks):
            callback(object())                     # Basic.Cancel frame from the broker
        await asyncio.wait_for(task, 1)

    asyncio.run(go())
    assert connection.closed is True


def test_aio_pika_glue_notices_a_cancelled_consumer_when_the_library_has_no_cancel_callback(monkeypatch):
    """aio-pika 9 (aiormq 6) has no cancel callback: on a Basic.Cancel it only drops the consumer
    from ``channel.consumers``. Found with a real RabbitMQ (tests/test_real_rabbitmq.py): the
    listening used to go on until the feed's silence limit."""
    import sys
    import types

    monkeypatch.setattr(amqp_feed, "CONSUMER_CHECK_SECONDS", 0.02)
    connection = _FakeConnection()
    del connection.channel_obj.channel.on_consumer_cancel_callbacks    # as in aiormq 6

    async def fake_connect(**kwargs):
        return connection

    monkeypatch.setitem(sys.modules, "aio_pika", types.SimpleNamespace(connect=fake_connect))

    async def go():
        task = asyncio.ensure_future(amqp_feed.consume_with_aio_pika(dict(DETAILS), lambda *a: None))
        await asyncio.sleep(0.15)                       # several checks with the consumer in place
        assert not task.done()
        connection.channel_obj.channel.consumers.clear()   # what aiormq 6 does on Basic.Cancel
        await asyncio.wait_for(task, 1)

    asyncio.run(go())
    assert connection.closed is True


def test_aio_pika_glue_still_works_when_the_library_has_no_cancel_hook(monkeypatch):
    import sys
    import types

    connection = _FakeConnection()
    del connection.channel_obj.channel                  # an older library without the hook

    async def fake_connect(**kwargs):
        return connection

    monkeypatch.setitem(sys.modules, "aio_pika", types.SimpleNamespace(connect=fake_connect))

    async def go():
        task = asyncio.ensure_future(amqp_feed.consume_with_aio_pika(dict(DETAILS), lambda *a: None))
        for _ in range(5):
            await asyncio.sleep(0)
        connection.close_callbacks.fire()
        await asyncio.wait_for(task, 1)

    asyncio.run(go())
    assert connection.closed is True


# --- an old error must not stay on after the feed works again (real HA, 3 October 2026) ------
def test_error_text_is_readable_when_the_exception_has_no_message():
    assert amqp_feed._safe_error(TimeoutError(), []) == "TimeoutError (no details)"
    assert amqp_feed._safe_error(TimeoutError("slow"), []) == "TimeoutError: slow"


def test_last_error_is_cleared_when_readings_arrive_again_but_its_time_is_kept():
    client = _FakeClient([TimeoutError(), _sub()])

    async def consume(details, on_message):
        on_message("MID.O.101", b'{"Value": 1200}')

    feed, _ = _run_feed(client, consume, stop_after_sleeps=2)
    assert feed.state.messages == 1
    assert feed.state.last_error is None            # cleared by the first reading
    assert feed.state.last_error_at is not None     # but we still know when it happened


def test_last_error_stays_while_the_feed_is_still_failing():
    client = _FakeClient([TimeoutError(), _sub()])

    async def consume(details, on_message):
        return None                                 # connects, but no readings arrive

    feed, _ = _run_feed(client, consume, stop_after_sleeps=2)
    assert feed.state.last_error == "TimeoutError (no details)"


def test_a_failure_is_warned_once_and_its_repeats_are_only_debug(caplog):
    client = _FakeClient([api.AmperiumError("HTTP 503")] * 3)

    async def consume(details, on_message):
        raise AssertionError("never reached")

    with caplog.at_level("INFO", logger="amperium.amqp_feed"):
        _run_feed(client, consume, stop_after_sleeps=3)
    levels = [r.levelname for r in caplog.records if "live feed" in r.getMessage()]
    assert levels == ["WARNING"]


def test_backoff_runs_from_5_seconds_up_to_10_minutes():
    assert amqp_feed.BACKOFF_SECONDS[0] == 5
    assert amqp_feed.BACKOFF_SECONDS[-1] == 600
    assert list(amqp_feed.BACKOFF_SECONDS) == sorted(amqp_feed.BACKOFF_SECONDS)


def test_feed_waits_longer_and_longer_up_to_the_cap_and_stays_there():
    n = len(amqp_feed.BACKOFF_SECONDS)
    client = _FakeClient([api.AmperiumError("HTTP 503")] * (n + 2))

    async def consume(details, on_message):
        raise AssertionError("never reached")

    feed, sleeps = _run_feed(client, consume, stop_after_sleeps=n + 2)
    assert sleeps == [*amqp_feed.BACKOFF_SECONDS, 600, 600]
    assert feed.state.failures == n + 2


def test_a_quiet_meter_never_makes_the_feed_wait_longer_than_5_minutes():
    n = len(amqp_feed.BACKOFF_SECONDS)
    client = _FakeClient([_sub() for _ in range(n + 2)])

    async def consume(details, on_message):
        return None                                   # connects, but nothing ever arrives

    _feed, sleeps = _run_feed(client, consume, stop_after_sleeps=n + 2)
    assert max(sleeps) == amqp_feed.QUIET_BACKOFF_CAP_SECONDS == 300
    assert sleeps[:3] == [5, 15, 30]                  # the early waits are the same as for errors


def test_every_attempt_asks_for_a_new_subscription_and_never_reuses_an_old_one():
    def sub(queue):
        s = _sub()
        s.details["queueName"] = queue
        return s

    seen = []

    async def consume(details, on_message):
        seen.append(details["queueName"])

    client = _FakeClient([sub("q1"), sub("q2"), sub("q3")])
    _run_feed(client, consume, stop_after_sleeps=3)
    assert client.calls == 3 and seen == ["q1", "q2", "q3"]


def test_an_outage_is_one_warning_and_one_working_again(caplog):
    client = _FakeClient([api.AmperiumError("Network error: TimeoutError")] * 5 + [_sub()])

    async def consume(details, on_message):
        on_message("MID.O.101", b'{"Value": 1200}')

    with caplog.at_level("INFO", logger="amperium.amqp_feed"):
        feed, _ = _run_feed(client, consume, stop_after_sleeps=6)
    records = [r for r in caplog.records if "live feed" in r.getMessage()]
    warnings = [r for r in records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and "Network error: TimeoutError" in warnings[0].getMessage()
    assert sum("working again" in r.getMessage() for r in records) == 1
    assert feed.state.last_error is None             # cleared by the first reading


def test_a_changed_problem_is_warned_about_again(caplog):
    client = _FakeClient([api.AmperiumError("HTTP 503"), api.AmperiumError("HTTP 503"),
                          api.AmperiumError("Network error: TimeoutError")])

    async def consume(details, on_message):
        raise AssertionError("never reached")

    with caplog.at_level("INFO", logger="amperium.amqp_feed"):
        _run_feed(client, consume, stop_after_sleeps=3)
    warned = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warned) == 2 and "HTTP 503" in warned[0] and "TimeoutError" in warned[1]


def test_a_quiet_meter_is_logged_once_at_info_not_every_minute(caplog):
    client = _FakeClient([_sub(), _sub(), _sub()])

    async def consume(details, on_message):
        return None                                   # connects, then the connection ends

    with caplog.at_level("INFO", logger="amperium.amqp_feed"):
        _run_feed(client, consume, stop_after_sleeps=3)
    records = [r for r in caplog.records if "connection ended" in r.getMessage()]
    assert [r.levelname for r in records] == ["INFO"]


def test_identical_details_after_a_failure_are_noted_without_showing_them():
    async def consume(details, on_message):
        raise ConnectionError("ACCESS_REFUSED - Login was refused")

    client = _FakeClient([_sub(), _sub()])
    feed, _ = _run_feed(client, consume, stop_after_sleeps=2)
    assert feed.state.last_error.endswith("(same connection details as the attempt before)")
    for secret in ("user-secret", "pw-secret", "queue-secret", "mq.example.test"):
        assert secret not in feed.state.last_error

    other = _sub()
    other.details["username"] = "other-user"
    client = _FakeClient([_sub(), other])
    feed, _ = _run_feed(client, consume, stop_after_sleeps=2)
    assert "same connection details" not in feed.state.last_error


def test_the_note_about_identical_details_goes_away_when_readings_arrive():
    calls = {"n": 0}

    async def consume(details, on_message):
        calls["n"] += 1
        if calls["n"] == 2:
            on_message("MID.O.101", b'{"Value": 1200}')
            return
        raise ConnectionError("ACCESS_REFUSED")

    client = _FakeClient([_sub(), _sub(), _sub()])
    feed, _ = _run_feed(client, consume, stop_after_sleeps=3)
    assert "same connection details" not in feed.state.last_error     # the 3rd failure starts over


# --- the live sensor is unavailable when nothing has arrived for 15 minutes -------------------
def test_the_feed_is_down_after_15_minutes_without_a_reading():
    state = amqp_feed.LiveFeedState()
    t0 = dt.datetime(2026, 11, 1, 20, 0, tzinfo=UTC)
    assert state.is_down(t0) is False and state.silent_seconds(t0) is None      # not started
    state.started_at = t0
    assert state.is_down(t0 + dt.timedelta(seconds=900)) is False
    assert state.is_down(t0 + dt.timedelta(seconds=901)) is True
    state.last_message_at = t0 + dt.timedelta(seconds=1000)                     # a reading arrives
    assert state.is_down(t0 + dt.timedelta(seconds=1000 + 900)) is False
    assert state.is_down(t0 + dt.timedelta(seconds=1000 + 901)) is True


def test_the_feed_records_when_it_started_and_when_the_latest_reading_arrived():
    async def consume(details, on_message):
        on_message("MID.O.101", b'{"Value": 1200}')

    feed, _ = _run_feed(_FakeClient([_sub()]), consume)
    assert feed.state.started_at is not None
    assert feed.state.last_message_at is not None
    assert feed.state.last_message_at >= feed.state.started_at


def test_a_buffered_reading_from_the_subscription_counts_as_a_reading_for_the_down_check():
    observed = dt.datetime.now(UTC) - dt.timedelta(seconds=5)

    async def consume(details, on_message):
        return None

    feed, _ = _run_feed(_FakeClient([_sub([(observed, 1500.0)])]), consume)
    assert feed.state.last_message_at == observed


def test_the_statuses_the_status_sensor_offers_are_all_the_feed_can_have():
    assert set(amqp_feed.LIVE_STATUSES) == {"off", "starting", "connecting", "connected", "error", "unavailable"}


# --- amperium.koble_til_live: drop the stream and subscribe again now -------------------------
def _start_feed(client, consume, monkeypatch, *, wait=30.0, backoff=None):
    """A feed that really waits (so a request can cut the wait short), run as a background task."""
    monkeypatch.setattr(amqp_feed, "BACKOFF_SECONDS", backoff or (wait,))
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        await asyncio.sleep(seconds)

    async def ensure():
        return True

    return amqp_feed.AmperiumLiveFeed(client, 7001, consume=consume, ensure_library=ensure, sleep=sleep), sleeps


async def _until(condition, seconds=2.0):
    for _ in range(int(seconds / 0.01)):
        if condition():
            return True
        await asyncio.sleep(0.01)
    return False


def test_a_reconnect_request_ends_a_long_wait_at_once(monkeypatch):
    async def consume(details, on_message):
        await asyncio.sleep(30)

    client = _FakeClient([api.AmperiumError("Network error: TimeoutError"), _sub()])
    feed, sleeps = _start_feed(client, consume, monkeypatch)

    async def go():
        task = asyncio.ensure_future(feed.run())
        assert await _until(lambda: client.calls == 1 and feed.state.status == "error")
        assert feed.state.failures == 1
        assert feed.request_reconnect() is True
        assert feed.state.failures == 0                         # the waiting starts over
        assert await _until(lambda: client.calls == 2), "it did not subscribe again"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert sleeps == [30.0]                                     # the 30 s wait was cut short


def test_a_reconnect_request_starts_the_waiting_over_from_the_shortest_wait(monkeypatch):
    async def consume(details, on_message):
        raise AssertionError("never reached")

    errors = [api.AmperiumError("HTTP 503")] * 3
    client = _FakeClient(errors)
    feed, sleeps = _start_feed(client, consume, monkeypatch, backoff=(30.0, 31.0, 32.0))

    async def go():
        task = asyncio.ensure_future(feed.run())
        assert await _until(lambda: client.calls == 1 and sleeps == [30.0])
        assert feed.request_reconnect()
        assert await _until(lambda: client.calls == 2 and len(sleeps) == 2)
        assert feed.request_reconnect()
        assert await _until(lambda: client.calls == 3 and len(sleeps) == 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert sleeps == [30.0, 30.0, 30.0]       # not 30, 31, 32: each request reset the count


def test_a_reconnect_request_drops_a_working_stream_and_subscribes_again(monkeypatch):
    cancelled = []

    async def consume(details, on_message):
        try:
            on_message("MID.O.101", b'{"Value": 1200}')
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    client = _FakeClient([_sub(), _sub()])
    feed, sleeps = _start_feed(client, consume, monkeypatch)

    async def go():
        task = asyncio.ensure_future(feed.run())
        assert await _until(lambda: feed.state.status == "connected" and feed.state.messages == 1)
        assert feed.request_reconnect() is True
        assert await _until(lambda: client.calls == 2), "it did not subscribe again"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert cancelled[0] is True                                 # the old stream was dropped
    assert sleeps == []                                         # and no waiting in between


def test_a_reconnect_request_does_nothing_when_the_feed_is_not_running():
    feed = amqp_feed.AmperiumLiveFeed(_FakeClient([]), 7001)
    assert feed.state.status == "off" and feed.request_reconnect() is False
    feed.state.set_status("unavailable")                        # the library could not be installed
    assert feed.request_reconnect() is False


def test_an_old_reconnect_request_does_not_cut_the_next_wait_short(monkeypatch):
    """A request made before an attempt starts is cleared by it; it does not skip the wait after."""
    async def consume(details, on_message):
        raise ConnectionError("ACCESS_REFUSED")

    client = _FakeClient([_sub()])
    feed, sleeps = _start_feed(client, consume, monkeypatch, wait=0.05)
    feed.state.set_status("connecting")
    feed.request_reconnect()                                    # leaves the flag set before the first attempt

    async def go():
        task = asyncio.ensure_future(feed.run())
        assert await _until(lambda: client.calls == 1)
        assert await _until(lambda: sleeps == [0.05])           # it waited: the old request was cleared
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
