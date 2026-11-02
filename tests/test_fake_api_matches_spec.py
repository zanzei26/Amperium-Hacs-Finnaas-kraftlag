"""The made-up Amperium answers used by tests_ha/ only use fields that are in the API description.

If the fake invented a field (or got a type wrong), the Home Assistant tests could pass while the
real API would answer differently. The fake is checked against the saved description in
tests/contract/swagger.json.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests_ha"))
import fake_api  # noqa: E402 - needs the path above

SPEC = json.loads((ROOT / "tests" / "contract" / "swagger.json").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
TYPES = {"number": (int, float), "integer": (int,), "string": (str,), "boolean": (bool,)}


def deref(schema):
    while "$ref" in schema:
        schema = SCHEMAS[schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def validate(body, schema, where):
    schema = deref(schema)
    if body is None:
        assert schema.get("nullable", False), f"{where} is null, the description does not allow it"
    elif schema.get("type") == "array":
        assert isinstance(body, list), where
        for i, item in enumerate(body):
            validate(item, schema["items"], f"{where}[{i}]")
    elif "properties" in schema or schema.get("type") == "object":
        assert isinstance(body, dict), where
        props = schema.get("properties", {})
        for key, value in body.items():
            assert key in props, f"{where}.{key} is not in the API description"
            validate(value, props[key], f"{where}.{key}")
    elif schema.get("type") in TYPES:
        assert isinstance(body, TYPES[schema["type"]]), f"{where} is {type(body).__name__}"
        assert not (isinstance(body, bool) and schema["type"] != "boolean"), where


def answer(path, method="GET", **kwargs):
    fake = fake_api.FakeAmperium()
    for key, value in kwargs.items():
        setattr(fake, key, value)
    status, body = asyncio.run(fake.request(None, method, path, json=kwargs.get("json")))
    assert status == 200
    return body


def schema_for(path, method):
    content = SPEC["paths"][path][method]["responses"]["200"]["content"]
    return next(iter(content.values()))["schema"]


@pytest.mark.parametrize(("path", "route", "method"), [
    ("/api/sites", "/api/sites", "get"),
    ("/api/sites/215/prices?from=2026-10-02T00:00:00Z&to=2026-10-02T06:00:00Z",
     "/api/sites/{siteId}/prices", "get"),
    ("/api/sites/215/consumption/energy?from=2026-08-31T22:00:00Z&to=2026-09-01T03:00:00Z&resolution=H",
     "/api/sites/{siteId}/consumption/energy", "get"),
    ("/api/sites/215/consumption/energy?from=2026-09-30T22:00:00Z&to=2026-10-01T03:00:00Z&resolution=H",
     "/api/sites/{siteId}/consumption/energy", "get"),
    ("/api/sites/215/consumption/charges?from=2026-08-31T22:00:00Z&to=2026-09-01T03:00:00Z&resolution=H",
     "/api/sites/{siteId}/consumption/charges", "get"),
    ("/api/sites/215/consumption/charges?from=2026-09-30T22:00:00Z&to=2026-10-01T03:00:00Z&resolution=H",
     "/api/sites/{siteId}/consumption/charges", "get"),
    ("/api/sites/215/stream/amqp", "/api/sites/{siteId}/stream/amqp", "post"),
    ("/api/accounts/login/refresh-token", "/api/accounts/login/refresh-token", "post"),
])
def test_the_fake_answers_only_use_fields_the_api_description_has(path, route, method):
    body = answer(path, method.upper())
    validate(body, schema_for(route, method), path.split("?")[0])


def test_the_fake_login_answer_matches_the_description():
    fake = fake_api.FakeAmperium()
    status, body = asyncio.run(fake.request(None, "POST", "/api/accounts/login/otp", json={"otp": "123456"}))
    assert status == 200
    validate(body, schema_for("/api/accounts/login/otp", "post"), "login")
