"""Cost and consumption for a free period (for the action ``amperium.hent_periode``).

The calculation itself lives in ``derived.summarise_period``; this fetches the answers it needs.
Norgespris is limited to the month's ceiling the way the invoice does it (see ``charges``): the
period's hourly figures are fetched in pieces that Amperium does not cut short, and the ceiling is
counted from the 1st of the month, also when the period starts later. No Home Assistant is needed,
so it can be tested with a fake client.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from .api import AmperiumClient
from .charges import (
    apply_cap,
    async_month_energy_before,
    async_uncapped_hourly_charges,
)
from .derived import summarise_period


async def async_period_summary(
    client: AmperiumClient,
    site_id: int,
    start: dt.datetime,
    end: dt.datetime,
    tz: dt.tzinfo,
    scheme: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Fetch hourly consumption and charges for [start, end) and summarise them.

    Raises AmperiumError (or AmperiumAuthError) if Amperium refuses a request.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    energy = await client.async_get_energy(site_id, start, end)
    charges = await client.async_get_charges(site_id, start, end)
    hourly = await async_uncapped_hourly_charges(client, site_id, start, end, energy, charges, now)
    # The ceiling counts from the 1st: add what the month had used before the period began.
    before = await async_month_energy_before(client, site_id, start, tz)
    capped = apply_cap(hourly, before + energy, now, tz)
    result = summarise_period(energy, {**charges, "energy": capped}, start, end, now, tz)
    result["scheme"] = scheme
    return result
