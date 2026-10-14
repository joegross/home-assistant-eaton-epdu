"""Integration-level tests: setup, coordinator first refresh, unload.

Uses the pytest-homeassistant-custom-component harness with a real Home
Assistant test instance. SNMP is mocked at the SnmpApi boundary — the
same data shape the live EMA112-10 returns (verified via snmpwalk).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eaton_epdu.const import DOMAIN

BASE = "1.3.6.1.4.1.534.6.6.7"

HOST_ENTRY_DATA = {
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


def snmp_results() -> dict:
    """Coordinator-shaped data as the live PDU returns it (EMA112-10)."""
    data = {
        # two presented units ("0,1" from unitsPresent)
        f"{BASE}.1.1.0": "0,1",
        # unit identities
        f"{BASE}.1.2.1.2.0": "ePDU MA 36U-C IN: 5-15P 12A 1P OUT: 16x5-15R",
        f"{BASE}.1.2.1.3.0": "EMA112-10",
        f"{BASE}.1.2.1.4.0": "U617F10048",
        f"{BASE}.1.2.1.5.0": "06.00.0003",
        f"{BASE}.1.2.1.6.0": "PDU",
        f"{BASE}.1.2.1.2.1": "ePDU MA 36U-C IN: 5-15P 12A 1P OUT: 16x5-15R",
        f"{BASE}.1.2.1.3.1": "EMA112-10",
        f"{BASE}.1.2.1.4.1": "U617F04001",
        f"{BASE}.1.2.1.5.1": "06.00.0003",
        f"{BASE}.1.2.1.6.1": "PDU",
        # counts (2 virtual inputs, 16 outlets each)
        f"{BASE}.1.2.1.20.0": 2,
        f"{BASE}.1.2.1.20.1": 2,
        f"{BASE}.1.2.1.22.0": 16,
        f"{BASE}.1.2.1.22.1": 16,
        # unit 0: custom name on outlet 3, factory elsewhere
        f"{BASE}.6.1.1.3.0.3": "nvr",
        f"{BASE}.6.1.1.3.0.1": "PDU 0 Outlet A1",
        f"{BASE}.6.1.1.6.0.3": "A3",
        f"{BASE}.6.1.1.6.0.1": "A1",
        # unit 0 outlet 3 status on
        f"{BASE}.6.6.1.2.0.3": 1,
        f"{BASE}.6.6.1.2.0.1": 1,
        # unit 1: custom names
        f"{BASE}.6.1.1.3.1.7": "robo",
        f"{BASE}.6.1.1.3.1.1": "PDU 1 Outlet A1",
        f"{BASE}.6.6.1.2.1.7": 1,
        f"{BASE}.6.6.1.2.1.1": 1,
        # input metrics
        f"{BASE}.3.2.1.3.0.1.1": 120000,
        f"{BASE}.3.3.1.4.0.1.1": 1879,
    }
    # input feed names and bulk-polled table rows: the coordinator walks
    # each count worth of rows with a trailing "unit." + "" index — the
    # walk OID passed to get_bulk ends in a dot (unit.index substituted
    # with index=""), so emit per-row keys for both units and both rows.
    for unit in ("0", "1"):
        data[f"{BASE}.3.1.1.10.{unit}."] = "L1"
        data[f"{BASE}.3.2.1.3.{unit}."] = 120000
        data[f"{BASE}.3.3.1.4.{unit}."] = 1879
        data[f"{BASE}.3.4.1.4.{unit}."] = 225
        data[f"{BASE}.3.4.1.5.{unit}."] = 1_000_000
        data[f"{BASE}.3.4.1.7.{unit}."] = 985
        for idx in range(1, 17):
            data[f"{BASE}.6.1.1.3.{unit}.{idx}"] = (
                "nvr" if (unit == "0" and idx == 3) else f"PDU {unit} Outlet A{idx}"
            )
            data[f"{BASE}.6.1.1.6.{unit}.{idx}"] = f"A{idx}"
            data[f"{BASE}.6.6.1.2.{unit}.{idx}"] = 1
            data[f"{BASE}.6.4.1.3.{unit}.{idx}"] = 100
            data[f"{BASE}.6.5.1.6.{unit}.{idx}"] = 950
            data[f"{BASE}.6.5.1.3.{unit}.{idx}"] = 12
            data[f"{BASE}.6.5.1.4.{unit}.{idx}"] = 5_000
    return data


def snmp_bulk(oids: list[str], count: int, api: dict) -> list[dict]:
    """Walk-shaped rows for get_bulk: OID ends dot + row indexes appended.

    The real API bulk-walks trailing-dot OIDs and returns a list of
    {full_oid: value} dicts, one per row. Each batch carries each OID's
    next `count` rows.
    """
    rows = []
    for i in range(1, count + 1):
        row = {}
        for base_oid in oids:
            # base_oid ends in "." (index substituted empty); the walk
            # appends the row index under the same parent
            row[f"{base_oid}{i}"] = api.get(f"{base_oid}{i}", 0)
        # also carry plain keys seen in api for single-OID probes
        for base_oid in oids:
            if base_oid in api:
                row[base_oid] = api[base_oid]
        rows.append(row)
    return rows


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _setup_entry(hass) -> MockConfigEntry:
    """Create a MockConfigEntry and set it up with SnmpApi mocked."""
    entry = MockConfigEntry(domain=DOMAIN, data=HOST_ENTRY_DATA)
    entry.add_to_hass(hass)

    api = snmp_results()
    with (
        patch(
            "custom_components.eaton_epdu.async_get_snmp_engine",
            return_value=object(),
        ),
        patch(
            "custom_components.eaton_epdu.SnmpApi.setup", AsyncMock()
        ),
        # get() for identity/count OIDs, get_bulk() for tables
        patch(
            "custom_components.eaton_epdu.SnmpApi.get",
            AsyncMock(side_effect=lambda oids: {o: api[o] for o in oids if o in api}),
        ),
        patch(
            "custom_components.eaton_epdu.SnmpApi.get_bulk",
            AsyncMock(side_effect=lambda oids, count: snmp_bulk(oids, count, api)),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


class TestSetupEntry:
    async def test_entry_loads(self, hass):
        entry = await _setup_entry(hass)
        assert entry.state is ConfigEntryState.LOADED

    async def test_both_units_create_one_device_each(self, hass):
        await _setup_entry(hass)
        from homeassistant.helpers import device_registry as dr

        devices = dr.async_get(hass).devices
        serials = {d.serial_number for d in devices.values()}
        assert serials == {"U617F10048", "U617F04001"}


class TestUnload:
    async def test_entry_unloads(self, hass):
        entry = await _setup_entry(hass)
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
