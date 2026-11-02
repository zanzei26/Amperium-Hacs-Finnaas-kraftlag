"""Fixtures for testing the integration in a real Home Assistant (pytest-homeassistant-custom-component).

Run with Python 3.14 and the packages in requirements-test-ha.txt:  pytest tests_ha
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fake_api import NOW, FakeAmperium

from custom_components.amperium.api import AmperiumClient

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
async def _home_assistant(recorder_mock, enable_custom_integrations, hass, freezer):
    """The set-up every test starts from.

    It is 2 October 2026, 12:30 in Norway (September is last month); Home Assistant loads
    custom_components/amperium from this repository. The recorder is a dependency of the
    integration, and its fixture has to be set up before ``hass``, so it is asked for first.
    """
    freezer.move_to(NOW)
    await hass.config.async_set_time_zone("Europe/Oslo")


@pytest.fixture
def api() -> FakeAmperium:
    """The fake Amperium API. Every HTTP call the client makes is answered by it."""
    fake = FakeAmperium()

    async def request(self, method, path, **kwargs):
        return await fake.request(self, method, path, **kwargs)

    with patch.object(AmperiumClient, "_request", request):
        yield fake
