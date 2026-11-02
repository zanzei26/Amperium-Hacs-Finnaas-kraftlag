"""The live power sensors (only with the Dobbe option on) and how they show a feed that is down."""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

from ha_helpers import entity_id, make_entry, setup_entry

from custom_components.amperium.amqp_feed import AmperiumLiveFeed


async def _idle(self):
    """A stand-in for the feed's loop that leaves the state to the test."""
    import asyncio

    self.state.started_at = self._now()
    self.state.set_status("connected")
    await asyncio.Event().wait()


async def _set_up(hass):
    with patch.object(AmperiumLiveFeed, "run", _idle):
        entry = await setup_entry(hass, make_entry(dobbe=True))
    return entry, entry.runtime_data.live_feed.state


def live_state(hass, entry):
    return hass.states.get(entity_id(hass, entry, "amperium_live_power"))


def status_state(hass, entry):
    return hass.states.get(entity_id(hass, entry, "amperium_live_status"))


async def test_the_live_sensors_exist_only_with_the_option_on(hass, api):
    entry = await setup_entry(hass, make_entry(dobbe=False))
    registry_keys = [s.entity_id for s in hass.states.async_all("sensor")]
    assert not any(name.endswith("amperium_live_status") for name in registry_keys)
    assert entry.runtime_data.live_feed is None


async def test_a_reading_is_shown_as_power_and_goes_stale_after_two_minutes(hass, api, freezer):
    entry, state = await _set_up(hass)
    now = dt.datetime.now(dt.timezone.utc)
    state.last_message_at = now
    state.set_import(1.5, now, now)
    await hass.async_block_till_done()
    assert live_state(hass, entry).state == "1.5"
    freezer.tick(dt.timedelta(minutes=3))
    state.notify()
    await hass.async_block_till_done()
    assert live_state(hass, entry).state == "unknown"          # stale, but the feed is not down yet


async def test_after_15_minutes_without_a_reading_the_sensor_is_unavailable_but_the_status_sensor_explains(
    hass, api, freezer
):
    entry, state = await _set_up(hass)
    state.set_status("error")
    state.last_error = "AmperiumError: Network error: TimeoutError"
    freezer.tick(dt.timedelta(minutes=16))
    state.notify()
    await hass.async_block_till_done()
    assert live_state(hass, entry).state == "unavailable"
    status = status_state(hass, entry)
    assert status.state == "error"
    assert status.attributes["feil"] == "AmperiumError: Network error: TimeoutError"
    assert status.attributes["down"] is True


async def test_the_sensor_comes_back_when_a_reading_arrives(hass, api, freezer):
    entry, state = await _set_up(hass)
    freezer.tick(dt.timedelta(minutes=16))
    state.notify()
    await hass.async_block_till_done()
    assert live_state(hass, entry).state == "unavailable"
    now = dt.datetime.now(dt.timezone.utc)
    state.last_error = None
    state.last_message_at = now
    state.set_import(2.25, now, now)
    await hass.async_block_till_done()
    assert live_state(hass, entry).state == "2.25"
    assert status_state(hass, entry).attributes["down"] is False
    assert status_state(hass, entry).attributes["siste_melding"] == now.isoformat()


async def test_the_status_sensor_is_not_written_for_every_reading(hass, api, freezer):
    entry, state = await _set_up(hass)
    status_id = entity_id(hass, entry, "amperium_live_status")
    writes = []
    hass.bus.async_listen("state_changed", lambda event: writes.append(event)
                          if event.data["entity_id"] == status_id else None)
    for _ in range(30):                                         # a reading every two seconds
        freezer.tick(dt.timedelta(seconds=2))
        now = dt.datetime.now(dt.timezone.utc)
        state.last_message_at = now
        state.set_import(1.0, now, now)
    await hass.async_block_till_done()
    assert len(writes) <= 3                                     # about one a minute, not thirty
