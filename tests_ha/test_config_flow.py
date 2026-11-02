"""Adding the integration, the options, and logging in again (the flows in config_flow.py)."""
from __future__ import annotations

from fake_api import PHONE, SITE_ID
from ha_helpers import make_entry, setup_entry
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.amperium.const import (
    CONF_ACCESS_TOKEN,
    CONF_HAS_DOBBE,
    CONF_PHONE,
    CONF_REFRESH_EXPIRES,
    CONF_REFRESH_TOKEN,
    CONF_SCHEME,
    CONF_SITE_ID,
    DOMAIN,
)


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def through_phone_and_code(hass, flow, phone="90000000", code="123456"):
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {CONF_PHONE: phone})
    assert result["step_id"] == "otp"
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": code})


async def test_the_flow_can_be_started_at_all(hass, api):
    """Home Assistant makes the flow object itself. Version 0.9.0 to 0.13.0 broke this (see CHANGELOG)."""
    result = await start(hass)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"


async def test_adding_the_integration_end_to_end(hass, api):
    flow = await start(hass)
    result = await through_phone_and_code(hass, flow)
    assert result["step_id"] == "scheme"                         # one site: no choosing
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SCHEME: "norgespris"})
    assert result["step_id"] == "dobbe"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HAS_DOBBE: False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_PHONE] == PHONE                              # 90000000 became +4790000000
    assert (data[CONF_ACCESS_TOKEN], data[CONF_REFRESH_TOKEN]) == ("login-access", "login-refresh")
    assert data[CONF_SITE_ID] == SITE_ID
    assert result["options"] == {CONF_SCHEME: "norgespris", CONF_HAS_DOBBE: False}
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is config_entries.ConfigEntryState.LOADED  # and it works straight away


async def test_an_account_with_several_sites_lets_you_choose(hass, api):
    api.extra_sites = [{"siteId": 300, "siteName": "Hytta"}]
    flow = await start(hass)
    result = await through_phone_and_code(hass, flow)
    assert result["step_id"] == "site"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SITE_ID: "215"})
    assert result["step_id"] == "scheme"


async def test_a_wrong_code_is_asked_for_again(hass, api):
    flow = await start(hass)
    result = await through_phone_and_code(hass, flow, code="000000")
    assert result["step_id"] == "otp" and result["errors"] == {"base": "invalid_otp"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": "123456"})
    assert result["step_id"] == "scheme"                          # and the right one goes through


async def test_too_many_codes_today_is_said_plainly(hass, api):
    api.otp_request_answer = (400, {"errorCode": 100104, "title": "Too many one time password requests"})
    result = await hass.config_entries.flow.async_configure(
        (await start(hass))["flow_id"], {CONF_PHONE: "90000000"})
    assert result["step_id"] == "user" and result["errors"] == {"base": "too_many_otp"}


async def test_amperium_failing_when_asking_for_a_code(hass, api):
    api.otp_request_answer = (500, None)
    result = await hass.config_entries.flow.async_configure(
        (await start(hass))["flow_id"], {CONF_PHONE: "90000000"})
    assert result["errors"] == {"base": "request_otp_failed"}


async def test_an_account_without_sites(hass, api):
    api.overrides["/api/sites"] = (200, [])
    flow = await start(hass)
    result = await through_phone_and_code(hass, flow)
    assert result["errors"] == {"base": "no_sites"}


async def test_the_same_site_cannot_be_added_twice(hass, api):
    await setup_entry(hass, make_entry())
    flow = await start(hass)
    result = await through_phone_and_code(hass, flow, phone=PHONE)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SCHEME: "subsidy"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HAS_DOBBE: False})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_changing_the_options_reloads_the_integration(hass, api):
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    coordinator = entry.runtime_data
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCHEME: "subsidy", CONF_HAS_DOBBE: False, "day_start": 7, "day_end": 21},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_SCHEME] == "subsidy" and entry.options["day_start"] == 7
    assert entry.runtime_data is not coordinator


async def test_the_day_must_start_before_it_ends(hass, api):
    entry = await setup_entry(hass, make_entry())
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCHEME: "norgespris", CONF_HAS_DOBBE: False, "day_start": 22, "day_end": 6},
    )
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "invalid_day_hours"}


async def test_logging_in_again_stores_the_new_tokens_and_keeps_the_rest(hass, api):
    entry = await setup_entry(hass, make_entry())
    entry.async_start_reauth(hass)
    await hass.async_block_till_done()
    flow = hass.config_entries.flow.async_progress_by_handler(DOMAIN)[0]
    assert flow["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    assert result["step_id"] == "reauth_otp"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": "123456"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert (entry.data[CONF_ACCESS_TOKEN], entry.data[CONF_REFRESH_TOKEN]) == ("login-access", "login-refresh")
    assert entry.data[CONF_REFRESH_EXPIRES] == "2027-10-02T10:30:00Z"
    assert entry.data[CONF_SITE_ID] == SITE_ID and entry.options[CONF_SCHEME] == "norgespris"
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_logging_in_again_with_a_wrong_code_asks_again(hass, api):
    entry = await setup_entry(hass, make_entry())
    entry.async_start_reauth(hass)
    await hass.async_block_till_done()
    flow = hass.config_entries.flow.async_progress_by_handler(DOMAIN)[0]
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": "999999"})
    assert result["step_id"] == "reauth_otp" and result["errors"] == {"base": "invalid_otp"}
    assert entry.data[CONF_ACCESS_TOKEN] == "access"              # nothing was overwritten
