"""A stand-in for api.amperium.cloud, to test the integration inside a real Home Assistant.

It replaces the one method that talks HTTP (``AmperiumClient._request``) and answers with
the same JSON shapes the real API gives. Everything above that (the client's parsing, the
coordinator, the entities) is the real code.

The numbers for September 2026 are those of an invented invoice (see tests/helpers.py), so a
test can check what a sensor shows against what that invoice says.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

UTC = dt.timezone.utc
SITE_ID = 7001
SITE_NAME = "Testveien 1"
PHONE = "+4790000000"

# --- September 2026, from the invented invoice -----------------------------------------------------
SEPT_START = dt.datetime(2026, 8, 31, 22, tzinfo=UTC)  # 1 Sept 00:00 Europe/Oslo
SEPT_END = dt.datetime(2026, 9, 30, 22, tzinfo=UTC)  # 1 Oct 00:00 Europe/Oslo
SEPT_HOURS = 720
SEPT_KWH = 1788.520
SEPT_HOURLY_ENERGY = 3110.40 + 84.10  # kraftpris + påslag, per month
SEPT_HOURLY_VAT = 643.90 - 5.00  # the VAT in the hours (the 5.00 on the fixed price is not in them)
SEPT_NORGESPRIS = 2236.80
SEPT_GRID_AFTER = -112.40
SEPT_SUBSIDY = 1342.65 + 112.40  # derived: nettleie 1342.65 = after + subsidy
SEPT_FIXED = 25.0

# --- October 2026, up to "now" (2 October 12:30 Oslo) ---------------------------------------
OCT_START = dt.datetime(2026, 9, 30, 22, tzinfo=UTC)  # 1 Oct 00:00 Europe/Oslo
NOW = dt.datetime(2026, 10, 2, 10, 30, tzinfo=UTC)  # 12:30 Oslo (summer time)


def iso(moment: dt.datetime) -> str:
    """The API's time format."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def hours_between(start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    """Start of every whole hour in [start, end)."""
    out, hour = [], start
    while hour < end:
        out.append(hour)
        hour += dt.timedelta(hours=1)
    return out


class FakeAmperium:
    """What the API answers. Change the attributes between calls to change the answers."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        # Hours (start, UTC) the API has no consumption/charges for.
        self.missing_hours: set[dt.datetime] = set()
        self.han_online: bool | None = True
        self.han_signal: int | None = 1
        self.energy_updated_on = "2026-10-02T09:00:00Z"
        # October sites figures (the API's own month totals).
        self.oct_hourly_kwh = 2.0
        self.oct_hourly_energy = 1.5
        self.oct_fixed = 25.0
        # Norgespris per kWh, and where Amperium cuts one request short: it stops adding
        # compensation after about this many kWh counted from the start of the request (None = never).
        self.oct_comp_per_kwh = 0.3
        self.amperium_cut_kwh: float | None = 4000.0
        # Answer 500 to a charges request shorter than 30 hours (the pieces of a long month).
        self.fail_short_charge_windows = False
        # Anything in here is returned as it is, for a path that starts with the key.
        self.overrides: dict[str, tuple[int, Any]] = {}
        # Called with (method, path) before answering; may raise to simulate a failure.
        self.hook: Callable[[str, str], None] | None = None
        # Logging in: the code the fake accepts, what asking for a code answers, more sites.
        self.valid_otp = "123456"
        self.otp_request_answer: tuple[int, Any] = (204, None)
        self.extra_sites: list[dict[str, Any]] = []
        self.stream_details: dict[str, Any] = {
            "server": "mq.example.test", "port": 5671, "useSsl": True, "virtualHost": "vh",
            "username": "u", "password": "p", "queueName": "q", "exchangeName": "x",
        }

    # -- the entry point the patch calls -----------------------------------------------------
    async def request(self, client: Any, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
        self.calls.append((method, path))
        if self.hook is not None:
            self.hook(method, path)
        for prefix, answer in self.overrides.items():
            if path.startswith(prefix):
                return answer
        parsed = urlparse(path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        route = parsed.path
        if route == "/api/sites":
            return 200, [self._site(), *self.extra_sites]
        if route == "/api/accounts/login/request-otp":
            return self.otp_request_answer
        if route == "/api/accounts/login/otp":
            if (kwargs.get("json") or {}).get("otp") == self.valid_otp:
                return 200, {"accessToken": "login-access", "refreshToken": "login-refresh",
                             "accessTokenExpiresAt": "2026-10-07T10:30:00Z",
                             "refreshTokenExpiresAt": "2027-10-02T10:30:00Z"}
            return 401, {"title": "Invalid code"}
        if route.endswith("/consumption/charges") and self.fail_short_charge_windows:
            first, last = self._window(query)
            if last - first < dt.timedelta(hours=30):
                return 500, None
        if route == f"/api/sites/{SITE_ID}/prices":
            return 200, self._prices(query)
        if route == f"/api/sites/{SITE_ID}/consumption/energy":
            return 200, self._energy(query)
        if route == f"/api/sites/{SITE_ID}/consumption/charges":
            return 200, self._charges(query)
        if route == f"/api/sites/{SITE_ID}/stream/amqp" and method == "POST":
            return 200, {"activePowerPositive": [], "activePowerNegative": [],
                         "liveConnectionDetails": self.stream_details}
        if route == "/api/accounts/login/refresh-token":
            # The description says a refresh gives a new access token only (no new refresh token).
            return 200, {"accessToken": "new-access", "expiresIn": 432000,
                         "accessTokenExpiresAt": "2026-10-07T10:30:00Z"}
        return 404, None

    # -- answers ---------------------------------------------------------------------------------
    def _oct_hours(self) -> list[dt.datetime]:
        return [h for h in hours_between(OCT_START, NOW.replace(minute=0, second=0))
                if h not in self.missing_hours]

    def _site(self) -> dict[str, Any]:
        hours = self._oct_hours()
        kwh = len(hours) * self.oct_hourly_kwh
        energy = len(hours) * self.oct_hourly_energy + self.oct_fixed  # the fixed price is in it
        grid_after = 120.0
        return {
            "siteId": SITE_ID, "siteName": SITE_NAME,
            "hanPortMeterOnline": self.han_online, "hanPortMeterSignal": self.han_signal,
            "isProducingEnergy": False,
            "usageForCurrentMonth": {
                "currentActivePowerImport": 1.2, "energyImportThisMonth": kwh,
                "energyImportToday": 20.0, "energyUpdatedOn": self.energy_updated_on,
            },
            "chargesForCurrentMonth": {
                "totalAmount": energy + grid_after, "amountEnergy": energy,
                "amountGridRent": grid_after,
            },
            "currentEnergyPrice": {"spotOfficial": 0.5, "spotPreliminary": 0.5, "surcharge": 0.05,
                                   "salesTaxPercentage": 25},
        }

    def _prices(self, query: dict[str, str]) -> list[dict[str, Any]]:
        start = dt.datetime.strptime(query["from"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        end = dt.datetime.strptime(query["to"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if start >= NOW:  # tomorrow's prices are not published yet
            return []
        return [
            {"startTime": iso(h), "endTime": iso(h + dt.timedelta(hours=1)),
             "spotPreliminary": 0.5 + h.hour * 0.01, "spotOfficial": 0.5 + h.hour * 0.01,
             "surcharge": 0.05, "salesTaxPercentage": 25, "updatedOn": iso(NOW)}
            for h in hours_between(start, end)
        ]

    def _window(self, query: dict[str, str]) -> tuple[dt.datetime, dt.datetime]:
        parse = lambda text: dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)  # noqa: E731
        return parse(query["from"]), parse(query["to"])

    def _energy(self, query: dict[str, str]) -> list[dict[str, Any]]:
        start, end = self._window(query)
        sept = start < OCT_START
        per_hour = SEPT_KWH / SEPT_HOURS if sept else self.oct_hourly_kwh
        return [
            {"from": iso(h), "to": iso(h + dt.timedelta(hours=1)),
             "importedEnergy": per_hour, "exportedEnergy": 0.0}
            for h in hours_between(start, end)
            if h not in self.missing_hours and h < NOW
        ]

    def _charges(self, query: dict[str, str]) -> dict[str, Any]:
        start, end = self._window(query)
        if start < OCT_START:
            return self._charges_september(start, end)
        return self._charges_october(start, end)

    def _charges_september(self, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
        hours = [h for h in hours_between(start, end) if h not in self.missing_hours]
        return {
            "energy": [
                {"from": iso(h), "to": iso(h + dt.timedelta(hours=1)),
                 "importedEnergyAmount": SEPT_HOURLY_ENERGY / SEPT_HOURS,
                 "salesTaxAmount": SEPT_HOURLY_VAT / SEPT_HOURS,
                 "importedCompensationAmountNorgespris": SEPT_NORGESPRIS / SEPT_HOURS,
                 "importedCompensationEnergyNorgespris": SEPT_KWH / SEPT_HOURS}
                for h in hours
            ],
            # Energy incl. the fixed monthly price (Kraft 3219.50) plus the grid rent after subsidy.
            "totalAmount": 3219.50 + SEPT_GRID_AFTER,
            "gridRent": {
                "totalAmount": SEPT_GRID_AFTER, "compensationAmount": SEPT_SUBSIDY,
                "capacityChargeAveragePower": 8.17,
                "capacityInterval": {"powerMin": 5, "powerMax": 10, "amount": 400},
                "importedEnergyDay": 1236.350, "importedEnergyNight": 552.170,
                "energyChargeDayAmount": 550.93, "energyChargeNightAmount": 210.00,
                "electricityFeeAmount": 159.36, "enovaFeeAmount": 22.36,
                "membershipDiscountAmount": 0.0, "salesTaxAmount": 268.53,
            },
            "fixedCharges": {"totalAmount": SEPT_FIXED},
            "capacityChargeIntervals": _CAPACITY_TIERS,
        }

    def _charges_october(self, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
        hours = [h for h in hours_between(start, end)
                 if h not in self.missing_hours and h < NOW.replace(minute=0, second=0)]
        energy = len(hours) * self.oct_hourly_energy
        grid_after = 120.0
        rows = []
        counted = 0.0
        for h in hours:
            share = 1.0
            if self.amperium_cut_kwh is not None:
                share = min(1.0, max(0.0, (self.amperium_cut_kwh - counted) / self.oct_hourly_kwh))
                counted += self.oct_hourly_kwh
            rows.append(
                {"from": iso(h), "to": iso(h + dt.timedelta(hours=1)),
                 "importedEnergyAmount": self.oct_hourly_energy,
                 "salesTaxAmount": self.oct_hourly_energy * 0.2,
                 "importedCompensationAmountNorgespris":
                     self.oct_comp_per_kwh * self.oct_hourly_kwh * share,
                 "importedCompensationEnergyNorgespris": self.oct_hourly_kwh * share}
            )
        return {
            "energy": rows,
            "totalAmount": energy + self.oct_fixed + grid_after,
            "gridRent": {
                "totalAmount": grid_after, "compensationAmount": 40.0,
                "capacityChargeAveragePower": 6.5,
                "capacityInterval": {"powerMin": 5, "powerMax": 10, "amount": 400},
                "importedEnergyDay": 50.0, "importedEnergyNight": 22.0,
                "energyChargeDayAmount": 22.0, "energyChargeNightAmount": 8.0,
                "electricityFeeAmount": 6.4, "enovaFeeAmount": 0.9,
                "membershipDiscountAmount": 0.0, "salesTaxAmount": 10.0,
            },
            "fixedCharges": {"totalAmount": self.oct_fixed},
            "capacityChargeIntervals": _CAPACITY_TIERS,
        }


_CAPACITY_TIERS = [
    {"powerMin": 0, "powerMax": 2, "amount": 210},
    {"powerMin": 2, "powerMax": 5, "amount": 300},
    {"powerMin": 5, "powerMax": 10, "amount": 400},
    {"powerMin": 10, "powerMax": 15, "amount": 525},
]
