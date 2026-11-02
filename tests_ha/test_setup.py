"""Setting the integration up, taking it down, and what happens when Amperium says no."""
from __future__ import annotations

from ha_helpers import make_entry, setup_entry, value
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er

from custom_components.amperium.const import DOMAIN


async def test_the_integration_sets_up_and_creates_its_entities(hass, api):
    entry = await setup_entry(hass, make_entry())
    assert entry.state is ConfigEntryState.LOADED
    assert float(value(hass, entry, "energy_month")) == 72.0
    assert value(hass, entry, "han_online", "binary_sensor") == "on"
    assert hass.services.has_service(DOMAIN, "hent_periode")
    assert hass.services.has_service(DOMAIN, "koble_til_live")


async def test_unloading_removes_the_entry_and_the_services(hass, api):
    entry = await setup_entry(hass, make_entry())
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not hass.services.has_service(DOMAIN, "hent_periode")
    assert not hass.services.has_service(DOMAIN, "koble_til_live")


async def test_a_login_that_is_no_longer_valid_starts_re_authentication(hass, api):
    api.overrides["/api/sites"] = (401, None)
    api.overrides["/api/accounts/login/refresh-token"] = (400, {"errorCode": 7})
    entry = await setup_entry(hass, make_entry())
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_amperium_being_down_makes_home_assistant_try_again_later(hass, api):
    api.overrides["/api/sites"] = (503, None)
    entry = await setup_entry(hass, make_entry())
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []   # not a login problem


async def test_login_valid_until_is_not_created_without_a_date_and_an_old_one_is_removed(hass, api):
    entry = make_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_login_valid_until", config_entry=entry
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(old.entity_id) is None
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_login_valid_until") is None
    # "Login renews at" does not depend on that date and is still there.
    assert value(hass, entry, "login_renews_at") == "2026-10-07T10:30:00+00:00"


async def test_login_valid_until_is_created_when_amperium_gave_a_date(hass, api):
    entry = await setup_entry(hass, make_entry(refresh_expires_at="2027-09-15T08:00:00Z"))
    assert value(hass, entry, "login_valid_until") == "2027-09-15T08:00:00+00:00"


async def test_a_token_refresh_does_not_reload_the_integration_but_a_changed_option_does(hass, api):
    entry = await setup_entry(hass, make_entry())
    coordinator = entry.runtime_data
    hass.config_entries.async_update_entry(entry, data={**entry.data, "access_token": "other"})
    await hass.async_block_till_done()
    assert entry.runtime_data is coordinator            # tokens changed: nothing restarted
    hass.config_entries.async_update_entry(entry, options={**entry.options, "has_dobbe": False, "day_start": 7})
    await hass.async_block_till_done()
    assert entry.runtime_data is not coordinator        # an option changed: reloaded
    assert entry.state is ConfigEntryState.LOADED
