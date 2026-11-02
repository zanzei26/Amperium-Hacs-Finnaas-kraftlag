"""The two actions: amperium.hent_periode and amperium.koble_til_live."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from ha_helpers import make_entry, setup_entry
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.amperium.amqp_feed import AmperiumLiveFeed
from custom_components.amperium.const import DOMAIN


async def call(hass, service, data, **kwargs):
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, **kwargs)


async def test_hent_periode_for_september_matches_the_invoice(hass, api):
    await setup_entry(hass, make_entry(scheme="norgespris"))
    out = await call(hass, "hent_periode", {"fra": "2026-09-01", "til": "2026-10-01"},
                     return_response=True)
    assert out["warnings"] == []
    assert out["hours_expected"] == out["hours_with_data"] == 720
    assert out["consumption_kwh"] == pytest.approx(1788.520)
    assert out["energy_gross"] == pytest.approx(3219.50, abs=0.005)          # Kraft
    assert out["fixed_monthly_price"] == 25.0                                # inside Kraft
    assert out["vat_on_energy"] == pytest.approx(643.90, abs=0.005)
    assert out["grid_before_support"] == pytest.approx(1342.65, abs=0.005)   # Nettleie
    assert out["capacity_charge"] == 400.0
    assert out["norgespris_compensation"] == pytest.approx(2236.80, abs=0.005)
    assert out["house_cost_norgespris"] == pytest.approx(2325.35, abs=0.005)  # Totalt
    assert out["price_per_kwh_norgespris"] == pytest.approx(1.3002, abs=5e-5)
    assert "fixed_fee" not in out


async def test_hent_periode_warns_about_a_period_over_a_month_end(hass, api):
    await setup_entry(hass, make_entry())
    out = await call(hass, "hent_periode", {"fra": "2026-09-30", "til": "2026-10-02"},
                     return_response=True)
    assert "period_spans_months" in out["warnings"]


async def test_hent_periode_rejects_a_period_that_ends_before_it_starts(hass, api):
    await setup_entry(hass, make_entry())
    with pytest.raises(ServiceValidationError):
        await call(hass, "hent_periode", {"fra": "2026-10-01", "til": "2026-09-01"},
                   return_response=True)


async def test_hent_periode_says_so_when_amperium_fails(hass, api):
    await setup_entry(hass, make_entry())
    api.overrides["/api/sites/7001/consumption/energy"] = (500, None)
    with pytest.raises(HomeAssistantError, match="Amperium"):
        await call(hass, "hent_periode", {"fra": "2026-09-01", "til": "2026-10-01"},
                   return_response=True)


async def test_koble_til_live_is_refused_without_a_dobbe_module(hass, api):
    await setup_entry(hass, make_entry(dobbe=False))
    with pytest.raises(ServiceValidationError, match="Dobbe"):
        await call(hass, "koble_til_live", {})


async def _hold_connected(self):
    """A stand-in for the live feed's loop: it says it is connected and waits."""
    import asyncio

    self.state.started_at = self._now()
    self.state.set_status("connected")
    await asyncio.Event().wait()


async def test_koble_til_live_asks_the_running_feed_to_reconnect(hass, api):
    with patch.object(AmperiumLiveFeed, "run", _hold_connected):
        entry = await setup_entry(hass, make_entry(dobbe=True))
        feed = entry.runtime_data.live_feed
        assert feed is not None
        await call(hass, "koble_til_live", {})
        assert feed._wake.is_set()          # the loop is told to stop waiting and subscribe again


async def test_koble_til_live_explains_when_the_feed_is_not_running(hass, api):
    async def never_started(self):
        return None                         # status stays "off", like when aio-pika is missing

    with patch.object(AmperiumLiveFeed, "run", never_started):
        await setup_entry(hass, make_entry(dobbe=True))
        with pytest.raises(HomeAssistantError, match="kjører ikke"):
            await call(hass, "koble_til_live", {})


async def test_an_entry_id_that_does_not_exist_is_refused(hass, api):
    await setup_entry(hass, make_entry())
    with pytest.raises(ServiceValidationError):
        await call(hass, "koble_til_live", {"entry_id": "nope"})
