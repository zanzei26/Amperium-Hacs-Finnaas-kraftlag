"""Tests for the free-period summary (amperium.hent_periode)."""
from __future__ import annotations

import asyncio

import pytest
from conftest import api, period
from helpers import (
    OSLO,
    PERIOD_NOW,
    _sept_inputs,
)


# --- period.async_period_summary, with a fake client -------------------------------------------
class _PeriodClient:
    def __init__(self, energy, charges):
        self.energy, self.charges, self.calls = energy, charges, []

    async def async_get_energy(self, site_id, start, end):
        self.calls.append(("energy", site_id, start, end))
        return self.energy

    async def async_get_charges(self, site_id, start, end):
        self.calls.append(("charges", site_id, start, end))
        return self.charges


def test_period_helper_asks_for_both_answers_for_the_same_window_and_adds_the_scheme():
    start, end, hours, charges = _sept_inputs()
    client = _PeriodClient(hours, charges)
    out = asyncio.run(period.async_period_summary(client, 215, start, end, OSLO, "norgespris", now=PERIOD_NOW))
    assert [c[0] for c in client.calls] == ["energy", "charges"]
    assert all(c[1:] == (215, start, end) for c in client.calls)
    assert out["scheme"] == "norgespris"
    assert out["house_cost_norgespris"] == pytest.approx(2864.30, abs=0.005)


def test_period_helper_lets_amperium_errors_through():
    class Failing(_PeriodClient):
        async def async_get_charges(self, site_id, start, end):
            raise api.AmperiumError("HTTP 500")

    start, end, hours, charges = _sept_inputs()
    with pytest.raises(api.AmperiumError):
        asyncio.run(period.async_period_summary(Failing(hours, charges), 215, start, end, OSLO))
