"""Norgespris compensation with the ceiling the invoice applies (0.15.0).

The invoice gives Norgespris for the first 5 000 kWh of each calendar month, counted from the 1st
in the order the hours came. Amperium's hourly compensation figures are right, but when one request
holds more than about 4 000 kWh counted from the start of the request, Amperium stops adding
compensation (the total of such a request comes out too low, without any warning). Checked against
five invoices (see README, "Norgespris-taket"): the sum of shorter requests equals the invoice's
Norgespris line, the sum of one long request does not.

So this module (1) cuts a long window into requests that are each well under that point, so the
hourly figures are complete, and (2) applies the invoice's own ceiling to the complete hours.
No Home Assistant is needed here, so it can be tested with a fake client.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from .derived import complete_hours, local_month_bounds

# The invoice's ceiling per calendar month (households; a holiday home has a lower one, which is
# not handled).
NORGESPRIS_CAP_KWH = 5000.0

# A request holding fewer kWh than this is never cut short by Amperium (it stops at about 4 000).
SAFE_REQUEST_KWH = 3000.0


def plan_windows(
    energy: list[dict[str, Any]],
    start: dt.datetime,
    end: dt.datetime,
    now: dt.datetime,
    max_kwh: float = SAFE_REQUEST_KWH,
) -> list[tuple[dt.datetime, dt.datetime]]:
    """Cut [start, end) into consecutive windows that each hold at most ``max_kwh`` of consumption.

    ``energy`` is the hourly consumption of the whole window. One window is returned when it all
    fits, and then no extra requests are needed. The windows cover [start, end) without gaps.
    """
    windows: list[tuple[dt.datetime, dt.datetime]] = []
    window_start = start
    total = 0.0
    for bucket in complete_hours(energy, now):
        if not start <= bucket["start"] < end:
            continue
        kwh = bucket["import"]
        if total > 0 and total + kwh > max_kwh:
            windows.append((window_start, bucket["start"]))
            window_start = bucket["start"]
            total = 0.0
        total += kwh
    windows.append((window_start, end))
    return windows


async def async_uncapped_hourly_charges(
    client: Any,
    site_id: int,
    start: dt.datetime,
    end: dt.datetime,
    energy: list[dict[str, Any]],
    whole: dict[str, Any],
    now: dt.datetime,
) -> list[dict[str, Any]]:
    """The hourly charge buckets of [start, end) with complete Norgespris figures.

    ``whole`` is the answer for the whole window (already fetched, for its totals). When the window
    fits in one safe request its hourly buckets are used as they are. Otherwise the window is asked
    for in pieces and the pieces are joined. Raises AmperiumError if a piece cannot be fetched.
    """
    windows = plan_windows(energy, start, end, now)
    if len(windows) == 1:
        return list(whole["energy"])
    buckets: list[dict[str, Any]] = []
    for window_start, window_end in windows:
        part = await client.async_get_charges(site_id, window_start, window_end)
        buckets += part["energy"]
    return buckets


async def async_month_energy_before(
    client: Any, site_id: int, start: dt.datetime, tz: dt.tzinfo
) -> list[dict[str, Any]]:
    """Hourly consumption from the first of the month up to ``start`` (empty when it starts on the 1st).

    The ceiling counts from the 1st, so a window that starts later needs what came before it.
    """
    _, month_start, _ = local_month_bounds(start.astimezone(tz))
    month_start_utc = month_start.astimezone(dt.timezone.utc)
    if month_start_utc >= start:
        return []
    return await client.async_get_energy(site_id, month_start_utc, start)


def apply_cap(
    charge_hours: list[dict[str, Any]],
    energy: list[dict[str, Any]],
    now: dt.datetime,
    tz: dt.tzinfo,
    cap_kwh: float = NORGESPRIS_CAP_KWH,
) -> list[dict[str, Any]]:
    """Limit Norgespris to the first ``cap_kwh`` of consumption in each local calendar month.

    ``energy`` must hold the consumption from the 1st of each month the charge hours belong to.
    An hour before the ceiling keeps its figures, an hour after it gets none, and the hour that
    crosses it gets the share that is under it. A bucket with no consumption row is left as it is
    (there is nothing to count it against). ``norgespris_cap_frac`` says what share was kept.
    A Norgespris figure that is None (unknown) stays None.
    """
    before: dict[dt.datetime, tuple[float, float]] = {}
    month: tuple[int, int] | None = None
    running = 0.0
    for bucket in complete_hours(energy, now):
        local = bucket["start"].astimezone(tz)
        if (local.year, local.month) != month:
            month = (local.year, local.month)
            running = 0.0
        before[bucket["start"]] = (running, bucket["import"])
        running += bucket["import"]

    out: list[dict[str, Any]] = []
    for bucket in charge_hours:
        known = before.get(bucket.get("start"))
        if known is None:
            out.append(bucket)
            continue
        counted, kwh = known
        frac = 1.0 if kwh <= 0 else min(1.0, max(0.0, (cap_kwh - counted) / kwh))
        scaled = dict(bucket)
        scaled["norgespris_cap_frac"] = frac
        for key in ("norgespris", "norgespris_kwh"):
            if scaled.get(key) is not None:
                scaled[key] = scaled[key] * frac
        out.append(scaled)
    return out


def unknown_norgespris(charge_hours: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The same buckets with the Norgespris figures marked unknown (when they cannot be trusted)."""
    return [{**b, "norgespris": None, "norgespris_kwh": None} for b in charge_hours]
