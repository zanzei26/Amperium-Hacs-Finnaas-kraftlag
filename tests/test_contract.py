"""The integration against Amperium's published API description (swagger).

Amperium has no agreement with us and can change its API without notice. This checks that every
endpoint, query parameter, request field and answer field the integration uses is in the API
description, with a type the code can read. It is run against a copy saved in
tests/contract/swagger.json, so it only changes when someone updates that copy. The weekly
workflow api-drift.yml runs the same checks against the live description
(AMPERIUM_SWAGGER=<file>) and reports what has changed.

What this does not cover: the description says what the API should answer, not what it does.
Fields the description leaves out (or gets wrong) are only found with a real answer. One example
is "resolution": the description calls it a plain string, but the real API only accepts a single
letter (H, D or M); that was found by trying, and it is not in the description.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from conftest import const

SPEC_PATH = Path(os.environ.get("AMPERIUM_SWAGGER") or Path(__file__).parent / "contract" / "swagger.json")
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]


def schema_of(operation, part):
    """The schema of a request body or a 200 answer (None if there is none)."""
    if part == "request":
        content = operation.get("requestBody", {}).get("content", {})
    else:
        content = operation.get("responses", {}).get("200", {}).get("content", {})
    schema = (content.get("application/json") or next(iter(content.values()), {})).get("schema")
    return schema


def resolve(schema):
    """Follow a $ref (and the item type of an array) down to an object schema."""
    while schema:
        if "$ref" in schema:
            schema = SCHEMAS[schema["$ref"].rsplit("/", 1)[-1]]
        elif schema.get("type") == "array":
            schema = schema["items"]
        else:
            return schema
    return {}


def kind(prop):
    """number, integer, string, boolean, array or object. An enum of numbers is an integer."""
    if "$ref" in prop:
        target = SCHEMAS[prop["$ref"].rsplit("/", 1)[-1]]
        return target.get("type", "object")
    return prop.get("type", "object")


# (HTTP method, path) -> what the integration sends and reads. A field is "name": "type"; the
# types are what the code can read (a number it turns into float, a string it parses, ...).
ENDPOINTS = {
    ("post", "/api/accounts/login/request-otp"): {
        "request": {"phoneNumber": "string"}},
    ("post", "/api/accounts/login/otp"): {
        "request": {"phoneNumber": "string", "otp": "string"},
        "answer": {"accessToken": "string", "refreshToken": "string",
                   "accessTokenExpiresAt": "string", "refreshTokenExpiresAt": "string"}},
    ("post", "/api/accounts/login/refresh-token"): {
        "request": {"accessToken": "string", "refreshToken": "string"},
        "answer": {"accessToken": "string", "accessTokenExpiresAt": "string"}},
    ("get", "/api/sites"): {
        "query": ["charges_from", "charges_to"],
        "answer": {"siteId": "integer", "siteName": "string", "hanPortMeterOnline": "boolean",
                   "hanPortMeterSignal": "integer", "isProducingEnergy": "boolean",
                   "usageForCurrentMonth": "object", "chargesForCurrentMonth": "object",
                   "currentEnergyPrice": "object"}},
    ("get", "/api/sites/{siteId}/prices"): {
        "query": ["from", "to"],
        "answer": {"startTime": "string", "endTime": "string", "spotPreliminary": "number",
                   "spotOfficial": "number", "surcharge": "number", "salesTaxPercentage": "number"}},
    ("get", "/api/sites/{siteId}/consumption/energy"): {
        "query": ["from", "to", "resolution"],
        "answer": {"from": "string", "to": "string", "importedEnergy": "number",
                   "exportedEnergy": "number"}},
    ("get", "/api/sites/{siteId}/consumption/charges"): {
        "query": ["from", "to", "resolution"],
        "answer": {"totalAmount": "number", "energy": "array", "gridRent": "object",
                   "fixedCharges": "object", "capacityChargeIntervals": "array"}},
    ("post", "/api/sites/{siteId}/stream/amqp"): {
        "request": {"includeActivePowerPositive": "boolean", "includeActivePowerNegative": "boolean",
                    "initializeFrom": "string", "liveFeedTtlInSeconds": "integer"},
        "answer": {"activePowerPositive": "array", "activePowerNegative": "array",
                   "liveConnectionDetails": "object"}},
}

# Nested objects in the answers: schema name -> fields the code reads.
OBJECTS = {
    "UsageData": {"currentActivePowerImport": "number", "energyImportThisMonth": "number",
                  "energyImportToday": "number", "energyExportThisMonth": "number",
                  "energyExportToday": "number", "energyUpdatedOn": "string"},
    "BillData": {"totalAmount": "number", "amountEnergy": "number", "amountGridRent": "number"},
    "SitePrice": {"spotOfficial": "number", "spotPreliminary": "number", "surcharge": "number",
                  "salesTaxPercentage": "number"},
    "EnergyCharges": {"from": "string", "to": "string", "importedEnergyAmount": "number",
                      "salesTaxAmount": "number", "importedCompensationAmountNorgespris": "number"},
    "GridRentCharges": {"totalAmount": "number", "compensationAmount": "number",
                        "salesTaxAmount": "number", "capacityChargeAveragePower": "number",
                        "capacityInterval": "object", "importedEnergyDay": "number",
                        "importedEnergyNight": "number", "energyChargeDayAmount": "number",
                        "energyChargeNightAmount": "number", "electricityFeeAmount": "number",
                        "enovaFeeAmount": "number", "membershipDiscountAmount": "number"},
    "FixedCharges": {"totalAmount": "number"},
    "CapacityChargeInterval": {"powerMin": "number", "powerMax": "number", "amount": "number"},
    "DoubleObservation": {"timestamp": "string", "value": "number"},
    "LiveConnectionDetails": {"server": "string", "port": "integer", "useSsl": "boolean",
                              "virtualHost": "string", "username": "string", "password": "string",
                              "queueName": "string", "exchangeName": "string"},
}


def check_fields(schema_name, props, expected):
    for name, want in expected.items():
        assert name in props, f"{schema_name} has no field {name!r} any more"
        have = kind(props[name])
        assert have == want, f"{schema_name}.{name} is {have}, the code expects {want}"


@pytest.mark.parametrize(("method", "path"), list(ENDPOINTS))
def test_the_endpoint_exists_with_the_parameters_the_code_sends(method, path):
    assert path in SPEC["paths"], f"{path} is gone from the API description"
    operation = SPEC["paths"][path].get(method)
    assert operation is not None, f"{method.upper()} {path} is gone"
    names = {p["name"] for p in operation.get("parameters", [])}
    for wanted in ENDPOINTS[(method, path)].get("query", []):
        assert wanted in names, f"{path} no longer takes the query parameter {wanted!r}"


@pytest.mark.parametrize(("method", "path"), [k for k, v in ENDPOINTS.items() if "request" in v])
def test_the_fields_the_code_sends_exist(method, path):
    operation = SPEC["paths"][path][method]
    props = resolve(schema_of(operation, "request")).get("properties", {})
    check_fields(f"{method.upper()} {path} request", props, ENDPOINTS[(method, path)]["request"])


@pytest.mark.parametrize(("method", "path"), [k for k, v in ENDPOINTS.items() if "answer" in v])
def test_the_fields_the_code_reads_exist_with_a_type_it_can_read(method, path):
    operation = SPEC["paths"][path][method]
    props = resolve(schema_of(operation, "answer")).get("properties", {})
    check_fields(f"{method.upper()} {path} answer", props, ENDPOINTS[(method, path)]["answer"])


@pytest.mark.parametrize("name", list(OBJECTS))
def test_the_nested_objects_have_the_fields_the_code_reads(name):
    assert name in SCHEMAS, f"{name} is gone from the API description"
    check_fields(name, SCHEMAS[name].get("properties", {}), OBJECTS[name])


def test_the_signal_is_a_level_from_0_to_4_not_dbm():
    levels = SCHEMAS["CellularSignalQuality"]
    assert levels.get("enum") == [0, 1, 2, 3, 4]


def test_the_live_feed_lifetime_we_ask_for_is_inside_what_the_api_allows():
    ttl = SCHEMAS["SubscriptionOptions"]["properties"]["liveFeedTtlInSeconds"]
    assert ttl["minimum"] <= const.LIVE_FEED_TTL_SECONDS <= ttl["maximum"]
