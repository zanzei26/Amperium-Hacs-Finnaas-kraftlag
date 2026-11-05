"""The coordinator: the HAN status between polls, missing hours, and the statistics."""
from __future__ import annotations

import datetime as dt
import logging

from fake_api import NOW, OCT_START
from ha_helpers import advance, make_entry, setup_entry, value
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

COORDINATOR = "custom_components.amperium.coordinator"


async def test_the_han_status_is_read_between_the_main_polls(hass, api, freezer, caplog):
    entry = await setup_entry(hass, make_entry())
    assert value(hass, entry, "han_online", "binary_sensor") == "on"
    sites_calls = [c for c in api.calls if c[1].startswith("/api/sites?")]
    api.han_online = False
    calls_before = len(api.calls)
    with caplog.at_level(logging.INFO, logger=COORDINATOR):
        await advance(hass, freezer, dt.timedelta(minutes=5, seconds=1))   # the main poll is every 15 minutes
    assert value(hass, entry, "han_online", "binary_sensor") == "off"
    assert "the HAN module is now offline" in caplog.text
    new = [c for c in api.calls if c[1].startswith("/api/sites?")][len(sites_calls):]
    assert len(new) == 1                                         # one cheap call, not a full poll
    assert [c[1].split("?")[0] for c in api.calls[calls_before:]] == ["/api/sites"]   # nothing else


async def test_a_han_status_that_did_not_change_writes_nothing_and_logs_nothing(hass, api, caplog):
    entry = await setup_entry(hass, make_entry())
    coordinator = entry.runtime_data
    before = hass.states.get("binary_sensor." + next(
        s.entity_id.split(".")[1] for s in hass.states.async_all("binary_sensor"))).last_updated
    with caplog.at_level(logging.INFO, logger=COORDINATOR):
        await coordinator.async_refresh_han_status()
    assert "HAN module is now" not in caplog.text
    after = hass.states.get("binary_sensor." + next(
        s.entity_id.split(".")[1] for s in hass.states.async_all("binary_sensor"))).last_updated
    assert before == after


async def test_a_failed_han_status_read_is_left_to_the_main_poll(hass, api):
    entry = await setup_entry(hass, make_entry())
    coordinator = entry.runtime_data
    api.overrides["/api/sites"] = (503, None)
    await coordinator.async_refresh_han_status()                 # no exception
    api.overrides["/api/sites"] = (401, None)
    api.overrides["/api/accounts/login/refresh-token"] = (400, {})
    await coordinator.async_refresh_han_status()                 # not even a login problem is raised here
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert value(hass, entry, "han_online", "binary_sensor") == "on"
    assert hass.config_entries.flow.async_progress() == []


async def test_missing_hours_are_logged_when_they_appear_and_when_they_arrive(hass, api, freezer, caplog):
    gone = {OCT_START + dt.timedelta(hours=10), OCT_START + dt.timedelta(hours=11)}
    api.missing_hours = set(gone)
    with caplog.at_level(logging.INFO, logger=COORDINATOR):
        entry = await setup_entry(hass, make_entry())
    assert value(hass, entry, "hours_missing_month") == "2"
    assert "no hourly data for 2 hour(s)" in caplog.text
    caplog.clear()
    api.missing_hours.clear()                                    # Amperium delivers them late
    with caplog.at_level(logging.INFO, logger=COORDINATOR):
        await advance(hass, freezer, dt.timedelta(hours=1, minutes=1))   # the month is read again every hour
    assert "2 hour(s) that were missing in the hourly data have arrived" in caplog.text
    assert value(hass, entry, "hours_missing_month") == "0"


async def _consumption_rows(hass):
    await async_wait_recording_done(hass)
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, OCT_START - dt.timedelta(days=1), NOW + dt.timedelta(days=1),
        {"amperium:7001_energy_import"}, "hour", None, {"change"},
    )
    return {dt.datetime.fromtimestamp(r["start"], dt.timezone.utc): r["change"]
            for r in rows.get("amperium:7001_energy_import", [])}


async def test_hourly_consumption_is_imported_as_statistics_and_a_late_hour_is_filled_in(hass, api, freezer):
    late = OCT_START + dt.timedelta(hours=10)
    api.missing_hours = {late}
    await setup_entry(hass, make_entry())
    rows = await _consumption_rows(hass)
    assert OCT_START in rows and rows[OCT_START] == 2.0
    assert late not in rows                                      # no data for it, nothing invented
    api.missing_hours.clear()
    await advance(hass, freezer, dt.timedelta(hours=1, minutes=1))
    rows = await _consumption_rows(hass)
    assert rows[late] == 2.0                                     # picked up by the next hourly read


async def test_advance_waits_for_the_scheduled_read_even_when_the_database_is_slow(hass, api, freezer):
    """The hourly read runs as a background task, so ``advance`` has to wait for it explicitly.

    Regression test for a flaky test: on a busy machine the helper returned while the import was
    still in progress, and the test then read the statistics before the late hour was written.
    Every read the import makes is slowed down here, so the helper returns early every time
    unless it really waits: both series must have been written when it returns.
    """
    import time
    from unittest.mock import patch

    from custom_components.amperium import statistics as stats

    real_read = stats.statistics_during_period
    real_add = stats.async_add_external_statistics
    written: list[str] = []

    def slow_read(*args, **kwargs):
        time.sleep(0.3)
        return real_read(*args, **kwargs)

    def add(hass_, metadata, rows):
        written.append(metadata["statistic_id"])
        return real_add(hass_, metadata, rows)

    await setup_entry(hass, make_entry())
    written.clear()
    with (
        patch.object(stats, "statistics_during_period", slow_read),
        patch.object(stats, "async_add_external_statistics", add),
    ):
        await advance(hass, freezer, dt.timedelta(hours=1, minutes=1))
        assert sorted(written) == ["amperium:7001_energy_cost", "amperium:7001_energy_import"]


async def test_a_failing_statistics_import_does_not_stop_the_sensors(hass, api, caplog):
    from unittest.mock import patch

    with patch(f"{COORDINATOR}.async_import_statistics", side_effect=RuntimeError("db is busy")):
        entry = await setup_entry(hass, make_entry())
    assert entry.state is ConfigEntryState.LOADED
    assert float(value(hass, entry, "energy_month")) == 72.0
    assert "Could not import statistics" in caplog.text


async def test_failed_prices_do_not_make_the_consumption_sensors_unavailable(hass, api):
    api.overrides["/api/sites/7001/prices"] = (500, None)
    entry = await setup_entry(hass, make_entry())
    assert entry.state is ConfigEntryState.LOADED
    assert float(value(hass, entry, "energy_month")) == 72.0


async def test_failed_hourly_data_keeps_the_last_good_values(hass, api, freezer):
    entry = await setup_entry(hass, make_entry())
    before = value(hass, entry, "net_cost_last_month")
    api.overrides["/api/sites/7001/consumption"] = (500, None)
    await advance(hass, freezer, dt.timedelta(hours=1, minutes=1))
    assert value(hass, entry, "net_cost_last_month") == before
