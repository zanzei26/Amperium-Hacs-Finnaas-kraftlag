"""Cost and consumption for a free period (for the action ``amperium.hent_periode``).

The calculation itself lives in ``derived.summarise_period``; this only fetches the two
answers it needs. No Home Assistant is needed, so it can be tested with a fake client.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from .api import AmperiumClient
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

    Raises AmperiumError (or AmperiumAuthError) if Amperium refuses either request.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    energy = await client.async_get_energy(site_id, start, end)
    charges = await client.async_get_charges(site_id, start, end)
    result = summarise_period(energy, charges, start, end, now, tz)
    result["scheme"] = scheme
    return result
