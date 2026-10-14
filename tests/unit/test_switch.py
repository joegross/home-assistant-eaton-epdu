"""Unit tests for eaton_epdu switch behavior.

Covers the pending-state mapping, rename propagation through the
coordinator update path, and availability when the status OID is absent.
"""

from __future__ import annotations

import pytest

from eaton_epdu.const import (  # noqa: E402
    SNMP_OID_OUTLETS_STATUS,
    SNMP_OID_UNITS_DEVICE_NAME,
    SNMP_OID_UNITS_PART_NUMBER,
    SNMP_OID_UNITS_PRODUCT_NAME,
    SNMP_OID_UNITS_SERIAL_NUMBER,
)
from eaton_epdu.switch import SnmpSwitchEntity  # noqa: E402

BASE = "1.3.6.1.4.1.534.6.6.7"

UNIT = "0"
INDEX = "3"
STATUS_OID = SNMP_OID_OUTLETS_STATUS.replace("unit", UNIT).replace(
    "index", INDEX
)
UNIT_META = {
    SNMP_OID_UNITS_PRODUCT_NAME.replace("unit", UNIT): "ePDU MA",
    SNMP_OID_UNITS_PART_NUMBER.replace("unit", UNIT): "EMA112-10",
    SNMP_OID_UNITS_SERIAL_NUMBER.replace("unit", UNIT): "U617F10048",
    SNMP_OID_UNITS_DEVICE_NAME.replace("unit", UNIT): "PDU",
}


class FakeCoordinator:
    def __init__(self, data):
        self.data = data

    def get_units(self):
        return ["0"]

    async def async_refresh(self):
        pass


def make_switch(data: dict) -> SnmpSwitchEntity:
    return SnmpSwitchEntity(FakeCoordinator(data), UNIT, INDEX)


def data_with(status) -> dict:
    return {**UNIT_META, STATUS_OID: status}


class TestPendingStateMapping:
    """Eaton: 0=off, 1=on, 2=pendingOff, 3=pendingOn (PR #70 semantics)."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(0, False), (1, True), (2, False), (3, True)],
    )
    def test_is_on_mapping(self, raw, expected):
        assert make_switch(data_with(raw)).is_on is expected

    def test_missing_status_unavailable(self):
        sw = make_switch({**UNIT_META})
        assert sw.available is False

    @pytest.mark.parametrize("raw", [0, 1, 2, 3])
    def test_present_status_available(self, raw):
        assert make_switch(data_with(raw)).available is True


class TestSwitchNaming:
    def test_switch_name_uses_outlet_label_chain(self):
        from eaton_epdu.const import SNMP_OID_OUTLETS_NAME

        name_oid = SNMP_OID_OUTLETS_NAME.replace("unit", UNIT).replace(
            "index", INDEX
        )
        sw = make_switch({**UNIT_META, STATUS_OID: 1, name_oid: "nvr"})
        assert sw._attr_name == "PDU nvr Switch"

    def test_switch_name_factory_default(self):
        from eaton_epdu.const import SNMP_OID_OUTLETS_DESIGNATOR

        designator_oid = SNMP_OID_OUTLETS_DESIGNATOR.replace(
            "unit", UNIT
        ).replace("index", INDEX)
        sw = make_switch({**UNIT_META, STATUS_OID: 1, designator_oid: "A3"})
        assert "Outlet A3" in sw._attr_name


class TestRenamePropagation:
    def test_display_name_follows_coordinator_update(self):
        from eaton_epdu.const import SNMP_OID_OUTLETS_NAME
        from eaton_epdu.const import SNMP_OID_OUTLETS_DESIGNATOR

        name_oid = SNMP_OID_OUTLETS_NAME.replace("unit", UNIT).replace(
            "index", INDEX
        )
        designator_oid = SNMP_OID_OUTLETS_DESIGNATOR.replace(
            "unit", UNIT
        ).replace("index", INDEX)
        data = {
            **UNIT_META,
            STATUS_OID: 1,
            designator_oid: "A3",
            name_oid: "PDU 0 Outlet A3",
        }
        sw = make_switch(data)
        before = sw._attr_name
        assert "Outlet A3" in before

        # rename lands in the data dict, coordinator broadcasts the update
        data[name_oid] = "nvr"
        sw._handle_coordinator_update()
        assert sw._attr_name == "PDU nvr Switch"
        assert "Outlet A3" not in sw._attr_name

    def test_unique_id_stable_across_rename(self):
        from eaton_epdu.const import SNMP_OID_OUTLETS_NAME

        name_oid = SNMP_OID_OUTLETS_NAME.replace("unit", UNIT).replace(
            "index", INDEX
        )
        data = {**UNIT_META, STATUS_OID: 1, name_oid: "old"}
        sw = make_switch(data)
        uid_before = sw._attr_unique_id
        data[name_oid] = "new"
        sw._handle_coordinator_update()
        assert sw._attr_unique_id == uid_before
