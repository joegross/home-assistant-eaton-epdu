"""Config flow tests: form path, full walk, duplicate-host behavior.

Real HA test instance; SnmpApi mocked at the network boundary with
data shapes from the live EMA112-10.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from tests.integration.test_init import snmp_bulk, snmp_results
from custom_components.eaton_epdu.const import DOMAIN

USER_INPUT = {
    "name": "PDU",
    "host": "pdu.home.stimpy.net",
    "port": 161,
    "update_interval": 60,
    "accurate_power": False,
    "version": "1",
    "version_write": "None",
    "community": "public",
    "community_write": "private",
    "username": "",
    "username_write": "",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def api_patches():
    api = snmp_results()
    return (
        patch(
            "custom_components.eaton_epdu.async_get_snmp_engine",
            return_value=object(),
        ),
        patch("custom_components.eaton_epdu.SnmpApi.setup", AsyncMock()),
        patch(
            "custom_components.eaton_epdu.SnmpApi.get",
            AsyncMock(side_effect=lambda oids: {o: api[o] for o in oids if o in api}),
        ),
        patch(
            "custom_components.eaton_epdu.SnmpApi.get_bulk",
            AsyncMock(side_effect=lambda oids, count: snmp_bulk(oids, count, api)),
        ),
    )


from contextlib import ExitStack  # noqa: E402


class multi_patch:
    """with multi_patch(*mocks) -> stacked context manager for patches."""

    def __init__(self, *mocks):
        self._mocks = mocks

    def __enter__(self):
        self._stack = ExitStack()
        for m in self._mocks:
            self._stack.enter_context(m)
        return self._stack

    def __exit__(self, *exc):
        return self._stack.__exit__(*exc)


def start_flow(hass):
    return hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_config_flow_completes(hass):
    """Submitting user input across the host + v1 steps creates an entry."""
    with multi_patch(*api_patches()):
        result = await start_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "host"

        # Step 1: host (version=v1 → advances to community step)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {k: v for k, v in USER_INPUT.items() if k not in ("community", "community_write", "username", "username_write")},
        )
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "v1"

        # Step 2: v1 write=None → creates the entry
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"community": "public"},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "pdu.home.stimpy.net"


async def test_config_flow_duplicate_host(hass):
    """The integration has no unique-host gate: second entry also created."""
    with multi_patch(*api_patches()):
        result = await start_flow(hass)
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {k: v for k, v in USER_INPUT.items() if k not in ("community", "community_write", "username", "username_write")},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"community": "public"}
        )
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.CREATE_ENTRY

        result2 = await start_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {k: v for k, v in USER_INPUT.items() if k not in ("community", "community_write", "username", "username_write")},
        )
        result2 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], {"community": "public"}
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
