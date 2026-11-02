"""Tests for the API client (token refresh, requests, live subscription call, HAN status)."""
from __future__ import annotations

import asyncio
import datetime as dt

import aiohttp
import pytest
from conftest import api, derived
from helpers import (
    COMP,
    DETAILS,
    OSLO,
    UTC,
    _sub,
)


def test_price_bucket_has_consumer_field():
    bucket = api._normalise_price(
        {"startTime": "a", "endTime": "b", "spotPreliminary": 1.7, "spotOfficial": None,
         "surcharge": 0.04, "salesTaxPercentage": 25}
    )
    assert bucket["official"] is False
    assert bucket["consumer"] == pytest.approx((1.7 + 0.04) * 1.25)


def test_summarise_prices_includes_consumer():
    buckets = [
        api._normalise_price({"startTime": f"s{i}", "endTime": f"e{i}", "spotOfficial": p,
                              "surcharge": 0.04, "salesTaxPercentage": 25})
        for i, p in enumerate((1.0, 2.0, 3.0))
    ]
    out = api.summarise_prices(buckets)
    assert out["price_min_today"] == 1.0 and out["price_max_today"] == 3.0
    assert out["price_min_consumer"] == pytest.approx(1.04 * 1.25)
    assert out["price_avg_consumer"] == pytest.approx((2.04) * 1.25)


def _charges_response(total, comp, outer):
    raw = {
        "energy": [], "totalAmount": outer,
        "gridRent": {"capacityChargeAveragePower": 5.62,
                     "capacityInterval": {"powerMin": 5, "powerMax": 10, "amount": 400},
                     "importedEnergyDay": 91.204, "importedEnergyNight": 47.318,
                     "compensationAmount": comp, "totalAmount": total},
        "fixedCharges": {"totalAmount": 25},
        "capacityChargeIntervals": [{"powerMin": 5, "powerMax": 10, "amount": 400},
                                    {"powerMin": 10, "powerMax": 15, "amount": 525}],
    }

    class Client(api.AmperiumClient):
        async def _request(self, *args, **kwargs):
            return 200, raw

    start = dt.datetime(2026, 9, 30, 22, tzinfo=UTC)
    return asyncio.run(Client(None, "a", "r").async_get_charges(1, start, start + dt.timedelta(days=3)))


def test_grid_summary_capacity_and_day_night():
    out = derived.summarise_grid(_charges_response(247.15, COMP, 512.40), "")
    assert out["capacity_avg_kw"] == 5.62 and out["capacity_amount"] == 400
    assert out["capacity_headroom_kw"] == pytest.approx(4.38)
    assert out["capacity_details"]["next_tier_amount"] == 525
    assert out["grid_energy_day_kwh"] == 91.204 and out["grid_energy_night_kwh"] == 47.318


def test_last_month_figures_come_from_charges_response():
    out = derived.summarise_grid(_charges_response(-121.08, 1501.40, 3340.50), "_last_month")
    assert out["cost_last_month"] == 3340.50
    assert out["cost_grid_rent_last_month"] == -121.08
    assert out["cost_energy_last_month"] == pytest.approx(3461.58)


def test_api_has_no_norgespris_endpoint_any_more():
    assert not hasattr(api.AmperiumClient, "async_get_norgespris_vs_subsidy")


# --- token refresh: never look like a logout unless Amperium says so ----------------
class _ScriptedClient(api.AmperiumClient):
    """Client whose HTTP answers are scripted: path -> list of (status, body)."""

    def __init__(self, script, **kwargs):
        super().__init__(None, **kwargs)
        self._script = {k: list(v) for k, v in script.items()}
        self.calls = []
        self.paths = []  # full paths, with the query string
        self.bodies = []  # JSON bodies sent

    async def _request(self, method, path, **kwargs):
        self.paths.append(path)
        self.bodies.append(kwargs.get("json"))
        self.calls.append((method, path.split("?")[0]))
        key = path.split("?")[0]
        return self._script[key].pop(0)


REFRESH = "/api/accounts/login/refresh-token"


def test_refresh_success_stores_tokens_immediately():
    stored = []
    client = _ScriptedClient(
        {REFRESH: [(200, {"accessToken": "new-a", "refreshToken": "new-r"})]},
        access_token="old-a", refresh_token="old-r",
        on_tokens=stored.append,
    )
    assert asyncio.run(client.refresh()) is True
    assert len(stored) == 1  # stored right away, once
    assert stored[0]["access_token"] == "new-a"
    assert stored[0]["refresh_token"] == "new-r"
    assert (client.access_token, client.refresh_token) == ("new-a", "new-r")


def test_refresh_keeps_old_refresh_token_if_not_rotated():
    client = _ScriptedClient({REFRESH: [(200, {"accessToken": "new-a"})]},
                             access_token="old-a", refresh_token="old-r")
    assert asyncio.run(client.refresh()) is True
    assert client.refresh_token == "old-r"


@pytest.mark.parametrize("status", [400, 401, 403])
def test_refresh_rejected_means_log_in_again(status):
    stored = []
    client = _ScriptedClient({REFRESH: [(status, {"errorCode": 1})]},
                             access_token="a", refresh_token="r",
                             on_tokens=stored.append)
    assert asyncio.run(client.refresh()) is False
    assert stored == []


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_refresh_server_trouble_is_not_a_logout(status):
    client = _ScriptedClient({REFRESH: [(status, None)]}, access_token="a", refresh_token="r")
    with pytest.raises(api.AmperiumError) as err:
        asyncio.run(client.refresh())
    assert not isinstance(err.value, api.AmperiumAuthError)
    assert (client.access_token, client.refresh_token) == ("a", "r")  # untouched


def test_request_retried_after_successful_refresh():
    client = _ScriptedClient(
        {"/api/sites": [(401, None), (200, [{"siteId": 1}])],
         REFRESH: [(200, {"accessToken": "n", "refreshToken": "m"})]},
        access_token="o", refresh_token="p",
    )
    status, data = asyncio.run(client._auth_get("/api/sites"))
    assert (status, data) == (200, [{"siteId": 1}])
    assert [c[1] for c in client.calls] == ["/api/sites", REFRESH, "/api/sites"]


def test_expired_refresh_token_ends_as_auth_error():
    client = _ScriptedClient({"/api/sites": [(401, None)], REFRESH: [(400, {"errorCode": 7})]},
                             access_token="o", refresh_token="p")
    with pytest.raises(api.AmperiumAuthError):
        asyncio.run(client.async_get_sites())


def test_server_trouble_during_refresh_is_not_auth_error():
    client = _ScriptedClient({"/api/sites": [(401, None)], REFRESH: [(503, None)]},
                             access_token="o", refresh_token="p")
    with pytest.raises(api.AmperiumError) as err:
        asyncio.run(client.async_get_sites())
    assert not isinstance(err.value, api.AmperiumAuthError)


# --- v0.9.1: expiry times, one refresh at a time -----------------------------------
def test_refresh_stores_expiry_times_from_the_response():
    stored = []
    client = _ScriptedClient(
        {REFRESH: [(200, {
            "accessToken": "new-a", "refreshToken": "new-r",
            "accessTokenExpiresAt": "2026-10-08T12:00:00Z",
            "refreshTokenExpiresAt": "2027-10-03T12:00:00Z",
        })]},
        access_token="old-a", refresh_token="old-r",
        access_expires_at="2026-10-03T12:00:00Z", refresh_expires_at="2027-10-01T12:00:00Z",
        on_tokens=stored.append,
    )
    assert asyncio.run(client.refresh()) is True
    assert stored[0] == {
        "access_token": "new-a", "refresh_token": "new-r",
        "access_expires_at": "2026-10-08T12:00:00Z",
        "refresh_expires_at": "2027-10-03T12:00:00Z",
    }
    assert client.tokens() == stored[0]


def test_refresh_keeps_known_expiry_if_response_has_none():
    client = _ScriptedClient(
        {REFRESH: [(200, {"accessToken": "new-a"})]},
        access_token="o", refresh_token="r",
        access_expires_at="2026-10-03T12:00:00Z", refresh_expires_at="2027-10-01T12:00:00Z",
    )
    assert asyncio.run(client.refresh()) is True
    assert client.refresh_expires_at == "2027-10-01T12:00:00Z"
    assert client.access_expires_at == "2026-10-03T12:00:00Z"


def test_login_response_sets_tokens_and_expiry():
    client = _ScriptedClient({"/api/accounts/login/otp": [(200, {
        "accessToken": "a", "refreshToken": "r",
        "accessTokenExpiresAt": "2026-10-08T12:00:00Z",
        "refreshTokenExpiresAt": "2027-10-03T12:00:00Z",
    })]})
    asyncio.run(client.login_otp("12345678", "1234"))
    assert client.tokens() == {
        "access_token": "a", "refresh_token": "r",
        "access_expires_at": "2026-10-08T12:00:00Z",
        "refresh_expires_at": "2027-10-03T12:00:00Z",
    }


class _YieldingClient(_ScriptedClient):
    """Like _ScriptedClient, but lets other tasks run during every request."""

    async def _request(self, method, path, **kwargs):
        await asyncio.sleep(0)
        return await super()._request(method, path, **kwargs)


def test_simultaneous_401s_cause_exactly_one_refresh():
    client = _YieldingClient(
        {"/api/sites": [(401, None), (401, None), (200, [{"siteId": 1}]), (200, [{"siteId": 1}])],
         REFRESH: [(200, {"accessToken": "n", "refreshToken": "m"})]},
        access_token="o", refresh_token="p",
    )

    async def both():
        return await asyncio.gather(client._auth_get("/api/sites"), client._auth_get("/api/sites"))

    results = asyncio.run(both())
    assert results == [(200, [{"siteId": 1}]), (200, [{"siteId": 1}])]
    refreshes = [c for c in client.calls if c[1] == REFRESH]
    assert len(refreshes) == 1  # the second request reused the new token
    assert client.access_token == "n"


def test_simultaneous_401s_with_rejected_refresh_both_end_as_auth_error():
    client = _YieldingClient(
        {"/api/sites": [(401, None), (401, None)],
         REFRESH: [(400, {"errorCode": 7}), (400, {"errorCode": 7})]},
        access_token="o", refresh_token="p",
    )

    async def both():
        return await asyncio.gather(client.async_get_sites(), client.async_get_sites(),
                                    return_exceptions=True)

    results = asyncio.run(both())
    assert all(isinstance(r, api.AmperiumAuthError) for r in results)


def _sites_query(month_start):
    client = _ScriptedClient({"/api/sites": [(200, [])]}, access_token="a", refresh_token="r")
    asyncio.run(client.async_get_sites(month_start))
    return client.paths[0]


def test_sites_month_starts_at_local_midnight_in_summer_time():
    start = derived.local_month_bounds(dt.datetime(2026, 10, 3, 19, 45, tzinfo=OSLO))[1]
    # 1 October 00:00 in Oslo (UTC+2) is 22:00 UTC on 30 September, not 00:00 UTC.
    assert "charges_from=2026-09-30T22:00:00Z" in _sites_query(start)


def test_sites_month_starts_at_local_midnight_in_winter_time():
    start = derived.local_month_bounds(dt.datetime(2026, 12, 5, 12, tzinfo=OSLO))[1]
    assert "charges_from=2026-11-30T23:00:00Z" in _sites_query(start)  # UTC+1


def test_sites_month_start_is_independent_of_the_tz_it_is_given_in():
    in_utc = dt.datetime(2026, 9, 30, 22, tzinfo=UTC)
    in_oslo = dt.datetime(2026, 10, 1, 0, tzinfo=OSLO)
    assert _sites_query(in_utc).split("&")[0] == _sites_query(in_oslo).split("&")[0]


def test_sites_without_month_start_keeps_the_old_utc_month():
    query = _sites_query(None)
    assert "charges_from=" in query and "T00:00:00Z&" in query


def test_subscription_repr_hides_the_connection_details():
    assert "pw-secret" not in repr(_sub()) and "user-secret" not in repr(_sub())


# --- live subscription call (POST /api/sites/{id}/stream/amqp) -------------------------------
STREAM = "/api/sites/7001/stream/amqp"


def test_live_subscription_sends_what_the_app_sends_and_parses_the_answer():
    client = _ScriptedClient({STREAM: [(200, {
        "activePowerPositive": [{"timestamp": "2026-10-03T19:00:10Z", "value": 1400.0},
                                {"timestamp": "2026-10-03T19:00:00Z", "value": 1300.0}],
        "activePowerNegative": [],
        "liveConnectionDetails": DETAILS,
    })]}, access_token="a", refresh_token="r")
    sub = asyncio.run(client.async_create_live_subscription(7001))
    body = client.bodies[0]
    assert body["includeActivePowerPositive"] is True
    assert body["includeActivePowerNegative"] is False
    assert body["liveFeedTtlInSeconds"] == 300
    initial = dt.datetime.fromisoformat(body["initializeFrom"].replace("Z", "+00:00"))
    assert 170 <= (dt.datetime.now(UTC) - initial).total_seconds() <= 190  # 180 s back
    assert sub.details == DETAILS
    assert [v for _, v in sub.import_observations] == [1300.0, 1400.0]  # oldest first
    assert sub.export_observations == []


def test_live_subscription_with_empty_history_is_fine():
    client = _ScriptedClient({STREAM: [(200, {"activePowerPositive": [], "activePowerNegative": [],
                                              "liveConnectionDetails": DETAILS})]})
    assert asyncio.run(client.async_create_live_subscription(7001)).import_observations == []


def test_live_subscription_401_refreshes_the_token_once_and_asks_again():
    answer = {"activePowerPositive": [], "activePowerNegative": [], "liveConnectionDetails": DETAILS}
    client = _ScriptedClient(
        {STREAM: [(401, None), (200, answer)], REFRESH: [(200, {"accessToken": "n", "refreshToken": "m"})]},
        access_token="expired", refresh_token="r",
    )
    sub = asyncio.run(client.async_create_live_subscription(7001))
    assert sub.details == DETAILS
    assert [c[1] for c in client.calls] == [STREAM, REFRESH, STREAM]
    assert client.bodies[0] == client.bodies[2]          # the same request, asked again
    assert client.access_token == "n"


def test_live_subscription_401_with_a_refused_refresh_is_an_auth_error():
    client = _ScriptedClient({STREAM: [(401, None)], REFRESH: [(400, {"errorCode": 7})]},
                             access_token="a", refresh_token="r")
    with pytest.raises(api.AmperiumAuthError):
        asyncio.run(client.async_create_live_subscription(7001))
    assert [c[1] for c in client.calls] == [STREAM, REFRESH]


def test_live_subscription_server_trouble_during_a_refresh_is_not_an_auth_error():
    client = _ScriptedClient({STREAM: [(401, None)], REFRESH: [(503, None)]},
                             access_token="a", refresh_token="r")
    with pytest.raises(api.AmperiumError) as err:
        asyncio.run(client.async_create_live_subscription(7001))
    assert not isinstance(err.value, api.AmperiumAuthError)


@pytest.mark.parametrize("status,body", [(500, None), (404, {"title": "x"}), (200, None),
                                          (200, {}), (200, {"liveConnectionDetails": {"server": "s"}})])
def test_live_subscription_bad_answers_are_errors(status, body):
    client = _ScriptedClient({STREAM: [(status, body)]})
    with pytest.raises(api.AmperiumError) as err:
        asyncio.run(client.async_create_live_subscription(7001))
    assert not isinstance(err.value, api.AmperiumAuthError)


# --- "Spotpris nå" was unknown after midnight: no official price yet (4 October 2026) -------
def _local_day_buckets(day, prelim_by_utc_hour=None, official=None):
    """Hourly price buckets for one Europe/Oslo day, shaped like the API answer, then normalised."""
    start = dt.datetime.combine(day, dt.time.min, tzinfo=OSLO)
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time.min, tzinfo=OSLO)
    first, last = start.astimezone(UTC), end.astimezone(UTC)
    buckets, t = [], first
    while t < last:
        price = (prelim_by_utc_hour or {}).get(t.hour, 1.0 + t.hour * 0.001)
        buckets.append(api._normalise_price({
            "startTime": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endTime": (t + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "spotPreliminary": price,
            "spotOfficial": official,
            "surcharge": 0.0392,
            "salesTaxPercentage": 25,
        }))
        t += dt.timedelta(hours=1)
    return buckets


INCIDENT_DAY = dt.date(2026, 10, 4)           # summer time (UTC+2); all hours official=False


INCIDENT_PRICES = {13: 1.04544}               # 13:00-14:00 UTC, as in the report


def _old_sensor_value(data):
    """What the sensor showed before the fix: only the official price from /api/sites."""
    return data.get("spot_price")


def test_reproduces_the_report_unknown_right_after_midnight_in_summer_time():
    buckets = _local_day_buckets(INCIDENT_DAY, INCIDENT_PRICES)
    assert all(b["official"] is False for b in buckets)       # as in the report
    # 00:05 local on 4 October is 22:05 UTC on 3 October.
    now = dt.datetime(2026, 10, 3, 22, 5, tzinfo=UTC)
    data = {"spot_price": None, "spot_price_preliminary": None,
            "price_bucket_now": derived.current_price_bucket(buckets, now)}
    assert _old_sensor_value(data) is None                    # the bug: state unknown
    value, official = derived.current_spot_price(
        data["spot_price"], data["price_bucket_now"], data["spot_price_preliminary"])
    assert value == pytest.approx(1.0 + 22 * 0.001)           # the price of 22:00-23:00 UTC
    assert official is False


def test_reproduces_the_reported_hour_value_and_consumer_price():
    buckets = _local_day_buckets(INCIDENT_DAY, INCIDENT_PRICES)
    now = dt.datetime(2026, 10, 4, 13, 30, tzinfo=UTC)         # 15:30 local
    bucket = derived.current_price_bucket(buckets, now)
    assert bucket["start"] == "2026-10-04T13:00:00Z" and bucket["end"] == "2026-10-04T14:00:00Z"
    assert bucket["official"] is False
    assert bucket["spot"] == 1.04544
    assert bucket["consumer"] == pytest.approx(1.3558, abs=1e-4)
    assert derived.current_spot_price(None, bucket, None) == (1.04544, False)


@pytest.mark.parametrize("day,hours", [
    (dt.date(2026, 10, 4), 24),     # ordinary summer-time day (the report)
    (dt.date(2026, 12, 5), 24),     # ordinary winter-time day
    (dt.date(2026, 10, 25), 25),    # clocks go back: 25 hours
    (dt.date(2026, 3, 29), 23),     # clocks go forward: 23 hours
])
def test_current_hour_is_found_for_every_instant_of_a_local_day(day, hours):
    buckets = _local_day_buckets(day)
    assert len(buckets) == hours
    for bucket in buckets:
        start = dt.datetime.fromisoformat(bucket["start"].replace("Z", "+00:00"))
        for offset in (0, 1, 1799, 3599):   # first second, a bit later, mid hour, last second
            found = derived.current_price_bucket(buckets, start + dt.timedelta(seconds=offset))
            assert found is bucket


@pytest.mark.parametrize("day,first_utc", [
    (dt.date(2026, 10, 4), "2026-10-03T22:00:00Z"),    # midnight local = 22:00 UTC (summer)
    (dt.date(2026, 12, 5), "2026-12-04T23:00:00Z"),    # midnight local = 23:00 UTC (winter)
])
def test_the_first_minutes_after_local_midnight_use_the_first_bucket(day, first_utc):
    buckets = _local_day_buckets(day)
    assert buckets[0]["start"] == first_utc
    first = dt.datetime.fromisoformat(first_utc.replace("Z", "+00:00"))
    for minutes in (0, 1, 5, 59):
        assert derived.current_price_bucket(buckets, first + dt.timedelta(minutes=minutes)) is buckets[0]
    # the minute before midnight local still belongs to the previous day's list
    assert derived.current_price_bucket(buckets, first - dt.timedelta(minutes=1)) is None


def test_the_clock_change_hour_is_found_twice_in_local_time_but_is_two_different_buckets():
    """25 October 2026: 02:30 local happens twice (00:30 UTC and 01:30 UTC)."""
    buckets = _local_day_buckets(dt.date(2026, 10, 25))
    first = derived.current_price_bucket(buckets, dt.datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
    second = derived.current_price_bucket(buckets, dt.datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
    assert first is not second
    assert first["start"] == "2026-10-25T00:00:00Z" and second["start"] == "2026-10-25T01:00:00Z"


def test_a_bucket_ends_exclusive_and_the_list_end_gives_none():
    buckets = _local_day_buckets(INCIDENT_DAY)
    boundary = dt.datetime(2026, 10, 4, 13, 0, tzinfo=UTC)
    assert derived.current_price_bucket(buckets, boundary)["start"] == "2026-10-04T13:00:00Z"
    assert derived.current_price_bucket(buckets, boundary - dt.timedelta(seconds=1))["start"] == "2026-10-04T12:00:00Z"
    assert derived.current_price_bucket(buckets, dt.datetime(2026, 10, 4, 22, 0, tzinfo=UTC)) is None


def test_bad_buckets_are_skipped_not_fatal():
    good = _local_day_buckets(INCIDENT_DAY)[5]
    now = dt.datetime.fromisoformat(good["start"].replace("Z", "+00:00")) + dt.timedelta(minutes=10)
    junk = [None, "x", {}, {"start": None, "end": None}, {"start": "no", "end": "date"}, good]
    assert derived.current_price_bucket(junk, now) is good
    assert derived.current_price_bucket(None, now) is None
    assert derived.current_price_bucket([], now) is None


# === 0.13.0: robustness of the live feed, the HAN status and missing hours (1 November 2026) =======
# The live sensor was unknown for ~15 of 48 hours. The log showed "Network error: (trying again)"
# every 5.5 minutes (a 30 s time-out plus the 300 s wait), and 139 x ACCESS_REFUSED before that.
class _FailingSession:
    """A session whose request ends in the given exception, like aiohttp does."""

    def __init__(self, error):
        self.error = error

    def request(self, *args, **kwargs):
        error = self.error

        class Ctx:
            async def __aenter__(self):
                raise error

            async def __aexit__(self, *exc):
                return False

        return Ctx()


@pytest.mark.parametrize("error,expected", [
    (TimeoutError(), "Network error: TimeoutError"),             # a time-out has no text
    (TimeoutError("slow"), "Network error: slow"),
    (aiohttp.ClientConnectionError("reset"), "Network error: reset"),
])
def test_a_network_error_always_says_what_kind_it_was(error, expected):
    client = api.AmperiumClient(_FailingSession(error))
    with pytest.raises(api.AmperiumError) as err:
        asyncio.run(client._request("GET", "/api/sites"))
    assert str(err.value) == expected


# --- the HAN status between the main polls ----------------------------------------------------
def test_han_status_reads_online_signal_and_the_newest_data_from_the_sites_call():
    site = {"siteId": 7001, "hanPortMeterOnline": False, "hanPortMeterSignal": 1,
            "usageForCurrentMonth": {"energyUpdatedOn": "2026-11-01T22:00:00Z", "energyImportToday": 95.9},
            "chargesForCurrentMonth": {"totalAmount": 1.0}}
    client = _ScriptedClient({"/api/sites": [(200, [{"siteId": 1}, site])]}, access_token="a", refresh_token="r")
    out = asyncio.run(client.async_fetch_han_status(7001))
    assert out == {"han_online": False, "han_signal": 1, "updated": "2026-11-01T22:00:00Z"}
    assert client.paths[0].startswith("/api/sites?charges_from=")      # the call the main poll makes


def test_han_status_works_when_amperium_leaves_the_fields_out():
    client = _ScriptedClient({"/api/sites": [(200, [{"siteId": 7001}])]})
    assert asyncio.run(client.async_fetch_han_status(7001)) == {
        "han_online": None, "han_signal": None, "updated": None}


def test_han_status_without_sites_or_with_server_trouble_is_an_error_not_a_guess():
    for script in ({"/api/sites": [(200, [])]}, {"/api/sites": [(503, None)]}):
        client = _ScriptedClient(script)
        with pytest.raises(api.AmperiumError):
            asyncio.run(client.async_fetch_han_status(7001))


def test_the_main_fetch_still_returns_everything_it_did():
    site = {"siteId": 7001, "siteName": "x", "hanPortMeterOnline": True, "hanPortMeterSignal": 3,
            "isProducingEnergy": False,
            "usageForCurrentMonth": {"energyImportThisMonth": 10.0, "energyUpdatedOn": "2026-11-01T22:00:00Z"},
            "chargesForCurrentMonth": {"totalAmount": 5.0, "amountEnergy": 4.0, "amountGridRent": 1.0},
            "currentEnergyPrice": {}}
    client = _ScriptedClient({"/api/sites": [(200, [site])]})
    out = asyncio.run(client.async_fetch(7001))
    assert (out["energy_month"], out["cost_total"], out["han_online"], out["han_signal"], out["updated"]) == (
        10.0, 5.0, True, 3, "2026-11-01T22:00:00Z")
