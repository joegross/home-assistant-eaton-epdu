"""Unit tests for eaton_epdu entity label logic.

Standalone pytest suite (no Home Assistant installation required): the HA
module graph is stubbed in conftest.py so the component imports cleanly.

Covers get_outlet_label() precedence (user name > designator > index),
factory-default detection, legacy ePDUs, and rename propagation through
the coordinator update path.
"""

from __future__ import annotations

import pytest

from eaton_epdu.const import (  # noqa: E402  (path set in conftest)
    SNMP_OID_OUTLETS_DESIGNATOR,
    SNMP_OID_OUTLETS_NAME,
    SNMP_OID_UNITS_DEVICE_NAME,
    SNMP_OID_UNITS_PART_NUMBER,
    SNMP_OID_UNITS_PRODUCT_NAME,
    SNMP_OID_UNITS_SERIAL_NUMBER,
)
from eaton_epdu.entity import SnmpEntity  # noqa: E402

BASE = "1.3.6.1.4.1.534.6.6.7"


def name_oid(unit: str, index: str) -> str:
    return SNMP_OID_OUTLETS_NAME.replace("unit", unit).replace("index", index)


def designator_oid(unit: str, index: str) -> str:
    return SNMP_OID_OUTLETS_DESIGNATOR.replace("unit", unit).replace(
        "index", index
    )


def make_entity(data: dict, unit: str = "0") -> SnmpEntity:
    class FakeCoordinator:
        def __init__(self, d):
            self.data = d

    return SnmpEntity(FakeCoordinator(data), unit)


UNIT_META = {
    SNMP_OID_UNITS_PRODUCT_NAME.replace("unit", "0"): "ePDU MA",
    SNMP_OID_UNITS_PART_NUMBER.replace("unit", "0"): "EMA112-10",
    SNMP_OID_UNITS_SERIAL_NUMBER.replace("unit", "0"): "U617F10048",
    SNMP_OID_UNITS_DEVICE_NAME.replace("unit", "0"): "PDU",
}


class TestFactoryDefaultFallback:
    """Uncustomized ePDUs must label exactly as before (1.5.4 behavior)."""

    def test_factory_name_falls_to_designator(self):
        ent = make_entity(
            {
                **UNIT_META,
                name_oid("0", "1"): "PDU 0 Outlet A1",
                designator_oid("0", "1"): "A1",
            }
        )
        assert ent.get_outlet_label("1") == "Outlet A1"

    def test_empty_name_falls_to_designator(self):
        ent = make_entity(
            {**UNIT_META, designator_oid("0", "2"): "A2"}
        )
        assert ent.get_outlet_label("2") == "Outlet A2"

    def test_no_name_no_designator_falls_to_index(self):
        ent = make_entity({**UNIT_META})
        assert ent.get_outlet_label("16") == "Outlet 16"

    @pytest.mark.parametrize(
        "factory",
        [
            "PDU 0 Outlet A1",
            "PDU 1 Outlet B7",
            "PDU 10 Outlet A12",
            "PDU 0 Outlet A1 ",  # whitespace variant
        ],
    )
    def test_factory_name_variants_all_fall_through(self, factory):
        ent = make_entity(
            {
                **UNIT_META,
                name_oid("0", "1"): factory,
                designator_oid("0", "1"): "A1",
            }
        )
        assert ent.get_outlet_label("1") == "Outlet A1", factory


class TestCustomNameWins:
    """The feature: user-defined names take precedence on G3 ePDUs."""

    @pytest.mark.parametrize(
        ("name", "want"),
        [
            ("nvr", "nvr"),
            ("EdgeRouter", "EdgeRouter"),
            ("sonos-kitchen", "sonos-kitchen"),
            ("comcast-old", "comcast-old"),
        ],
    )
    def test_custom_name_beats_designator(self, name, want):
        ent = make_entity(
            {
                **UNIT_META,
                name_oid("0", "3"): name,
                designator_oid("0", "3"): "A3",
            }
        )
        assert ent.get_outlet_label("3") == want

    def test_unicode_name(self):
        ent = make_entity(
            {
                **UNIT_META,
                name_oid("0", "4"): "køkken",
                designator_oid("0", "4"): "A4",
            }
        )
        assert ent.get_outlet_label("4") == "køkken"


class TestLegacyEpdu:
    """Older ePDUs that expose names but no designators (PR #70 case)."""

    def test_legacy_name_without_designator(self):
        """Legacy unit (no designator OID): factory name falls to index."""
        ent = make_entity({name_oid("1", "7"): "PDU 1 Outlet A7"}, unit="1")
        assert ent.get_outlet_label("7") == "Outlet 7"

    def test_legacy_custom_name_without_designator(self):
        """Legacy unit with a real custom name still uses the name."""
        ent = make_entity({name_oid("1", "7"): "robo"}, unit="1")
        assert ent.get_outlet_label("7") == "robo"

    def test_legacy_name_not_re_prefixed(self):
        """Name already starting with 'Outlet ' must not double-prefix."""
        ent = make_entity({name_oid("1", "5"): "Outlet A5"}, unit="1")
        assert ent.get_outlet_label("5") == "Outlet A5"

    def test_missing_data_falls_to_index(self):
        ent = make_entity({}, unit="1")
        assert ent.get_outlet_label("16") == "Outlet 16"


class TestRenamePropagation:
    """Renaming on the PDU propagates through the coordinator data."""

    def test_label_changes_with_coordinator_data(self):
        data = {
            **UNIT_META,
            name_oid("0", "3"): "PDU 0 Outlet A3",
            designator_oid("0", "3"): "A3",
        }
        ent = make_entity(data)
        assert ent.get_outlet_label("3") == "Outlet A3"
        # ePDU web UI rename lands in the next poll
        data[name_oid("0", "3")] = "nvr"
        assert ent.get_outlet_label("3") == "nvr"

    def test_label_reverts_when_name_cleared(self):
        data = {**UNIT_META, name_oid("0", "9"): "gw", designator_oid("0", "9"): "A9"}
        ent = make_entity(data)
        assert ent.get_outlet_label("9") == "gw"
        data[name_oid("0", "9")] = ""
        assert ent.get_outlet_label("9") == "Outlet A9"


class TestUnitIsolation:
    """.replace() on shared OID templates must not leak across units."""

    def test_unit0_and_unit1_name_oids_are_distinct(self):
        assert name_oid("0", "3") != name_oid("1", "3")

    def test_unit_data_isolation(self):
        data = {
            **UNIT_META,
            name_oid("0", "3"): "nvr",
            name_oid("1", "3"): "sonos-kitchen",
        }
        ent0 = make_entity(data, unit="0")
        ent1 = make_entity(data, unit="1")
        assert ent0.get_outlet_label("3") == "nvr"
        assert ent1.get_outlet_label("3") == "sonos-kitchen"


class TestDeviceIdentity:
    """unique_id inputs must never depend on user-defined outlet names."""

    def test_identifier_prefers_serial(self):
        ent = make_entity({**UNIT_META})
        assert ent.identifier == "U617F10048"

    def test_identifier_missing_serial_falls_to_device_name(self):
        serial_key = SNMP_OID_UNITS_SERIAL_NUMBER.replace("unit", "0")
        data = {k: v for k, v in UNIT_META.items() if k != serial_key}
        ent = make_entity(data)
        assert ent.identifier == "PDU"

    def test_device_info_model_and_serial(self):
        ent = make_entity({**UNIT_META})
        info = ent.device_info
        assert info["serial_number"] == "U617F10048"
        assert info["model"] == "EMA112-10 ePDU MA"
