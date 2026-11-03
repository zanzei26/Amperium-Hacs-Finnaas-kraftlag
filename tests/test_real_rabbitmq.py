"""The live feed's connection code against a real RabbitMQ, not a fake.

The other tests replace aio-pika with a stand-in. These use the real library and a real
broker, and cover what a stand-in cannot show: that messages arrive the way the feed reads
them, and that the listening ends, instead of hanging, when the broker removes the queue
(a subscription that expires) or closes the connection.

They are skipped unless ``AMPERIUM_TEST_RABBITMQ_HOST`` is set. CI sets it in the job
``broker-tests`` (see .github/workflows/tests.yml), which runs a RabbitMQ container.
To run them by hand:

    docker run --rm -p 5672:5672 -p 15672:15672 -e RABBITMQ_DEFAULT_USER=test \\
        -e RABBITMQ_DEFAULT_PASS=test rabbitmq:3.13.7-management
    AMPERIUM_TEST_RABBITMQ_HOST=localhost AMPERIUM_TEST_RABBITMQ_USER=test \\
        AMPERIUM_TEST_RABBITMQ_PASSWORD=test pytest tests/test_real_rabbitmq.py -v

Not covered: TLS (Amperium uses port 5671; the test broker has no certificate) and the
oldest aio-pika the integration allows (9.0.0).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import os
import urllib.parse
import uuid

import aiohttp
import pytest
from conftest import amqp_feed, api

HOST = os.environ.get("AMPERIUM_TEST_RABBITMQ_HOST")
PORT = int(os.environ.get("AMPERIUM_TEST_RABBITMQ_PORT", "5672"))
MANAGEMENT_PORT = int(os.environ.get("AMPERIUM_TEST_RABBITMQ_MANAGEMENT_PORT", "15672"))
USER = os.environ.get("AMPERIUM_TEST_RABBITMQ_USER", "guest")
PASSWORD = os.environ.get("AMPERIUM_TEST_RABBITMQ_PASSWORD", "guest")
EXCHANGE = "amperium-test"

pytestmark = pytest.mark.skipif(
    not HOST, reason="no RabbitMQ to test against (set AMPERIUM_TEST_RABBITMQ_HOST)"
)
aio_pika = pytest.importorskip("aio_pika")


async def _admin():
    """A connection of the test's own, used to set the queues up and to check on them."""
    return await aio_pika.connect(
        host=HOST, port=PORT, login=USER, password=PASSWORD, virtualhost="/", timeout=10
    )


async def _new_subscription(channel) -> dict:
    """What Amperium's subscription call gives: details of a fresh queue fed by an exchange."""
    exchange = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC)
    queue = await channel.declare_queue(f"amperium-test-{uuid.uuid4().hex[:10]}")
    await queue.bind(exchange, routing_key="#")
    return {
        "server": HOST, "port": PORT, "useSsl": False, "virtualHost": "/",
        "username": USER, "password": PASSWORD,
        "queueName": queue.name, "exchangeName": EXCHANGE,
    }


async def _publish(channel, routing_key: str, payload) -> None:
    exchange = await channel.get_exchange(EXCHANGE)
    await exchange.publish(
        aio_pika.Message(body=json.dumps(payload).encode()), routing_key=routing_key
    )


async def _consumer_count(channel, queue_name: str) -> int:
    queue = await channel.declare_queue(queue_name, passive=True)
    return queue.declaration_result.consumer_count


async def _until(check, what: str, timeout: float = 15.0) -> None:
    """Wait for ``check()`` (a plain or an async function) to become true."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        result = check()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


async def _stop(task: asyncio.Future) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


def _noop(_key: str, _body: bytes) -> None:
    return None


def test_readings_published_to_the_exchange_reach_the_feed():
    async def scenario():
        admin = await _admin()
        channel = await admin.channel()
        details = await _new_subscription(channel)
        feed = amqp_feed.AmperiumLiveFeed(None, 7001)
        seen: list[tuple[str, bytes]] = []

        def on_message(key: str, body: bytes) -> None:
            seen.append((key, body))
            feed.handle_message(key, body)

        consumer = asyncio.ensure_future(amqp_feed.consume_with_aio_pika(details, on_message))
        try:
            await _until(
                lambda: _has_consumer(channel, details["queueName"]), "the consumer to attach"
            )
            await _publish(channel, "MID1.O.101", {"Timestamp": "2026-11-03T12:00:00Z", "Value": 1500})
            await _publish(channel, "MID1.O.101", {"t": "2026-11-03T12:00:02Z", "v": 2200})
            await _publish(channel, "MID1.O.102", {"Timestamp": "2026-11-03T12:00:03Z", "Value": 9})
            await _until(lambda: len(seen) == 3, "three messages")
        finally:
            await _stop(consumer)
            with contextlib.suppress(Exception):
                await channel.queue_delete(details["queueName"])
            await admin.close()
        return feed, seen

    feed, seen = asyncio.run(scenario())
    assert [key for key, _ in seen] == ["MID1.O.101", "MID1.O.101", "MID1.O.102"]
    assert json.loads(seen[0][1]) == {"Timestamp": "2026-11-03T12:00:00Z", "Value": 1500}
    # Two import readings count (watts -> kW); the other observation id is ignored.
    assert feed.state.messages == 2
    assert feed.state.import_kw == pytest.approx(2.2)
    assert feed.state.import_observed == dt.datetime(2026, 11, 3, 12, 0, 2, tzinfo=dt.timezone.utc)


async def _has_consumer(channel, queue_name: str) -> bool:
    return await _consumer_count(channel, queue_name) == 1


def test_the_listening_ends_when_the_broker_removes_the_queue():
    """An expired subscription: the broker cancels the consumer but leaves the connection open."""

    async def scenario():
        admin = await _admin()
        channel = await admin.channel()
        details = await _new_subscription(channel)
        consumer = asyncio.ensure_future(amqp_feed.consume_with_aio_pika(details, _noop))
        try:
            await _until(
                lambda: _has_consumer(channel, details["queueName"]), "the consumer to attach"
            )
            await channel.queue_delete(details["queueName"])
            await asyncio.wait_for(consumer, timeout=10)  # must end by itself
        finally:
            await _stop(consumer)
            await admin.close()

    asyncio.run(scenario())


def test_the_listening_ends_when_the_broker_closes_the_connection():
    async def scenario():
        admin = await _admin()
        channel = await admin.channel()
        details = await _new_subscription(channel)
        consumer = asyncio.ensure_future(amqp_feed.consume_with_aio_pika(details, _noop))
        base = f"http://{HOST}:{MANAGEMENT_PORT}/api"
        try:
            await _until(
                lambda: _has_consumer(channel, details["queueName"]), "the consumer to attach"
            )
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(USER, PASSWORD)) as http:
                found: list[str] = []

                async def connection_found() -> bool:
                    async with http.get(f"{base}/consumers") as answer:
                        for entry in await answer.json():
                            if entry["queue"]["name"] == details["queueName"]:
                                found.append(entry["channel_details"]["connection_name"])
                                return True
                    return False

                # The management API refreshes its figures every few seconds.
                await _until(connection_found, "the management API to list the consumer", 40)
                name = urllib.parse.quote(found[0], safe="")
                async with http.delete(f"{base}/connections/{name}") as answer:
                    assert answer.status in (200, 204)
            await asyncio.wait_for(consumer, timeout=10)  # must end by itself
        finally:
            await _stop(consumer)
            with contextlib.suppress(Exception):
                await channel.queue_delete(details["queueName"])
            await admin.close()

    asyncio.run(scenario())


def test_a_wrong_password_is_an_error_that_does_not_show_the_password():
    details = {
        "server": HOST, "port": PORT, "useSsl": False, "virtualHost": "/",
        "username": USER, "password": "not-the-password-8431", "queueName": "x",
    }

    async def scenario():
        await asyncio.wait_for(amqp_feed.consume_with_aio_pika(details, _noop), timeout=25)

    with pytest.raises(Exception) as caught:  # the type depends on aio-pika's version
        asyncio.run(scenario())
    assert not isinstance(caught.value, TimeoutError)
    text = amqp_feed._safe_error(caught.value, list(details.values()))
    assert "not-the-password-8431" not in text


def test_a_queue_that_does_not_exist_ends_the_listening_instead_of_hanging():
    async def scenario():
        admin = await _admin()
        channel = await admin.channel()
        details = await _new_subscription(channel)
        await channel.queue_delete(details["queueName"])  # gone before the feed gets there
        await admin.close()
        try:
            await asyncio.wait_for(amqp_feed.consume_with_aio_pika(details, _noop), timeout=15)
        except TimeoutError:
            raise AssertionError("the listening hung on a queue that does not exist") from None
        except Exception:  # noqa: BLE001 - an error is fine: the feed's loop handles it
            return

    asyncio.run(scenario())


class _Client:
    """Gives a fresh queue on every call, as Amperium does."""

    def __init__(self, channel) -> None:
        self._channel = channel
        self.details: list[dict] = []

    async def async_create_live_subscription(self, site_id, ttl_seconds=300):
        self.details.append(await _new_subscription(self._channel))
        return api.LiveSubscription(details=self.details[-1], import_observations=[])


def test_the_feed_takes_a_new_subscription_when_its_queue_is_removed():
    """The whole loop: connect, receive, lose the queue, subscribe again, receive again."""

    async def fast_sleep(_seconds: float) -> None:
        await asyncio.sleep(0.05)

    async def scenario():
        admin = await _admin()
        channel = await admin.channel()
        client = _Client(channel)
        feed = amqp_feed.AmperiumLiveFeed(client, 7001, sleep=fast_sleep)
        run = asyncio.ensure_future(feed.run())
        try:
            await _until(lambda: len(client.details) == 1, "the first subscription")
            first = client.details[0]["queueName"]
            await _until(lambda: _has_consumer(channel, first), "the first consumer")
            assert feed.state.status == "connected"
            await _publish(channel, "MID1.O.101", {"Timestamp": "2026-11-03T12:00:00Z", "Value": 1000})
            await _until(lambda: feed.state.import_kw == 1.0, "the first reading")

            await channel.queue_delete(first)
            await _until(lambda: len(client.details) == 2, "a second subscription", 20)
            second = client.details[1]["queueName"]
            await _until(lambda: _has_consumer(channel, second), "the second consumer")
            await _publish(channel, "MID1.O.101", {"Timestamp": "2026-11-03T12:01:00Z", "Value": 3000})
            await _until(lambda: feed.state.import_kw == 3.0, "the reading after the new subscription")
            assert feed.state.status == "connected"
        finally:
            await _stop(run)
            for details in client.details:
                with contextlib.suppress(Exception):
                    await channel.queue_delete(details["queueName"])
            await admin.close()
        return feed

    feed = asyncio.run(scenario())
    assert feed.state.messages == 2
