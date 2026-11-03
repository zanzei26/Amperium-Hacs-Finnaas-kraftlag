"""Helpers for the Home Assistant tests (building an entry, setting it up, finding entities)."""
from __future__ import annotations

from fake_api import PHONE, SITE_ID, SITE_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.amperium.const import (
    CONF_ACCESS_EXPIRES,
    CONF_ACCESS_TOKEN,
    CONF_HAS_DOBBE,
    CONF_PHONE,
    CONF_REFRESH_EXPIRES,
    CONF_REFRESH_TOKEN,
    CONF_SCHEME,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    DOMAIN,
)


def make_entry(*, dobbe: bool = False, scheme: str = "norgespris", **data) -> MockConfigEntry:
    """A config entry for the test site."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Amperium – {SITE_NAME}",
        unique_id=f"{PHONE}-{SITE_ID}",
        data={
            CONF_PHONE: PHONE,
            CONF_ACCESS_TOKEN: "access",
            CONF_REFRESH_TOKEN: "refresh",
            CONF_ACCESS_EXPIRES: "2026-10-07T10:30:00Z",
            CONF_REFRESH_EXPIRES: None,
            CONF_SITE_ID: SITE_ID,
            CONF_SITE_NAME: SITE_NAME,
            **data,
        },
        options={CONF_SCHEME: scheme, CONF_HAS_DOBBE: dobbe},
    )


async def setup_entry(hass, entry: MockConfigEntry) -> MockConfigEntry:
    """Add the entry to Home Assistant and set the integration up."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id(hass, entry: MockConfigEntry, key: str, platform: str = "sensor") -> str:
    """The entity id of one of our entities, found by its unique id (the id itself may change)."""
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert found is not None, f"no {platform} entity with key {key}"
    return found


def value(hass, entry: MockConfigEntry, key: str, platform: str = "sensor") -> str:
    """The state of one of our entities."""
    return hass.states.get(entity_id(hass, entry, key, platform)).state


async def advance(hass, freezer, delta) -> None:
    """Let time pass and wait until everything that was due has finished, the recorder included.

    A scheduled coordinator read runs as a *background task*, which a plain
    ``async_block_till_done()`` does not wait for: the helper then returned while the hourly
    import was still in progress, and a test that read the statistics straight afterwards
    sometimes saw them before they were written (a flaky test). So background tasks are
    waited for explicitly. That also means this helper is for entries without the live feed,
    whose task runs for as long as the entry is loaded and would never finish.

    The import writes through the recorder's own thread, so that is waited for too.
    """
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    from pytest_homeassistant_custom_component.components.recorder.common import (
        async_wait_recording_done,
    )

    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    await async_wait_recording_done(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
