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

from .api import AmperiumAuthError, AmperiumClient, AmperiumError
from .charges import (
    apply_cap,
    async_month_energy_before,
    async_uncapped_hourly_charges,
)
from .derived import summarise_period
from .spot import (
    kraft_from_prices,
    norgespris_from_prices,
    period_price_fields,
    trusted_norgespris,
)


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
    with_cap = {**charges, "energy": capped}
    result = summarise_period(energy, with_cap, start, end, now, tz)
    # The hourly prices are an extra (the weighted spot price, and Kraft rebuilt from the prices to
    # compare with Amperium's): if they cannot be fetched the rest of the answer still stands.
    try:
        prices: list | None = await client.async_get_prices(site_id, start, end)
    except AmperiumAuthError:
        raise
    except AmperiumError:
        prices = None
    fields, warnings = period_price_fields(
        energy, prices, start, end, now, result.get("energy_gross"), result.get("fixed_monthly_price")
    )
    # Amperium's Kraft is replaced by the one rebuilt from the prices when every hour has a price
    # and consumption: they agree to the øre in the months checked, but Amperium's answer is a few
    # kr too low for a request that crosses the autumn clock change (25 October 2026).
    rebuilt = kraft_from_prices(energy, prices, start, end, now, result.get("fixed_monthly_price"))
    # The same for the Norgespris compensation: Amperium's hourly figures leave out the hours around
    # the autumn clock change, which the prices do not. The ceiling counts from the 1st of the month.
    np_amperium = result.get("norgespris_compensation")
    np_rebuilt = norgespris_from_prices(before + energy, prices, start, end, now, tz)
    np_use = np_rebuilt if trusted_norgespris(np_amperium, np_rebuilt) else None
    np_diff = None if np_rebuilt is None or np_amperium is None else np_amperium - np_rebuilt[0]
    if rebuilt is not None or np_use is not None:
        result = summarise_period(
            energy, with_cap, start, end, now, tz,
            kraft_override=None if rebuilt is None else rebuilt[0],
            vat_override=None if rebuilt is None else rebuilt[1],
            norgespris_override=None if np_use is None else np_use[0],
            norgespris_kwh_override=None if np_use is None else np_use[1],
        )
    if rebuilt is not None:
        warnings = ["kraft_fra_priser_brukt" if w == "kraft_avviker_fra_priser" else w for w in warnings]
    if np_diff is not None:
        fields["norgespris_avvik_fra_priser"] = round(np_diff, 2)
        if np_use is None:
            warnings.append("norgespris_avviker_fra_priser")      # too far apart: Amperium's is kept
        elif abs(np_diff) > 1.0:
            warnings.append("norgespris_fra_priser_brukt")
    result.update(fields)
    result["warnings"] = [*result["warnings"], *warnings]
    result["scheme"] = scheme
    return result
