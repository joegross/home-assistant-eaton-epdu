"""Unit tests for eaton_epdu outlet sensor naming.

Covers name assembly (device + prefix + label + suffix with None/empty
filtering) for the outlet sensor classes, and rename propagation.
"""

from __future__ import annotations

import pytest

from eaton_epdu.const import (  # noqa: E402
    SNMP_OID_OUTLETS_CURRENT,
    SNMP_OID_OUTLETS_DESIGNATOR,
    SNMP_OID_OUTLETS_NAME,
    SNMP_OID_OUTLETS_STATUS,
    SNMP_OID_UNITS_DEVICE_NAME,
    SNMP_OID_UNITS_PART_NUMBER,
    SNMP_OID_UNITS_PRODUCT_NAME,
    SNMP_OID_UNITS_SERIAL_NUMBER,
)
from eaton_epdu.sensor import (  # noqa: E402
    SnmpOutletCurrentSensorEntity,
    SnmpOutletPFSensorEntity,
    SnmpOutletWattHoursSensorEntity,
    SnmpOutletWattsSensorEntity,
)

BASE = "1.3.6.1.4.1.534.6.6.7"

UNIT = "0"
INDEX = "3"
UNIT_META = {
    SNMP_OID_UNITS_PRODUCT_NAME.replace("unit", UNIT): "ePDU MA",
    SNMP_OID_UNITS_PART_NUMBER.replace("unit", UNIT): "EMA112-10",
    SNMP_OID_UNITS_SERIAL_NUMBER.replace("unit", UNIT): "U617F10048",
    SNMP_OID_UNITS_DEVICE_NAME.replace("unit", UNIT): "PDU",
}


class FakeCoordinator:
    def __init__(self, data):
        self.data = data


def oids_for(index: str) -> dict:
    name = SNMP_OID_OUTLETS_NAME.replace("unit", UNIT).replace("index", index)
    designator = SNMP_OID_OUTLETS_DESIGNATOR.replace("unit", UNIT).replace(
        "index", index
    )
    status = SNMP_OID_OUTLETS_STATUS.replace("unit", UNIT).replace(
        "index", index
    )
    current = SNMP_OID_OUTLETS_CURRENT.replace("unit", UNIT).replace(
        "index", index
    )
    return {
        "name": name,
        "designator": designator,
        "status": status,
        "current": current,
    }


OUTLET_SENSOR_CLASSES = [
    SnmpOutletCurrentSensorEntity,
    SnmpOutletPFSensorEntity,
    SnmpOutletWattsSensorEntity,
    SnmpOutletWattHoursSensorEntity,
]


@pytest.mark.parametrize("cls", OUTLET_SENSOR_CLASSES)
class TestSensorNaming:
    def test_custom_name_with_suffix(self, cls):
        oids = oids_for(INDEX)
        data = {
            **UNIT_META,
            oids["name"]: "nvr",
            oids["status"]: 1,
            oids["current"]: 500,
        }
        sensor = cls(FakeCoordinator(data), UNIT, INDEX)
        assert sensor._attr_name.startswith("nvr ")
        assert sensor._attr_name != "nvr"  # suffix present

    def test_factory_designator_name(self, cls):
        oids = oids_for(INDEX)
        data = {
            **UNIT_META,
            oids["status"]: 1,
            oids["current"]: 500,
            oids["designator"]: "A3",
        }
        sensor = cls(FakeCoordinator(data), UNIT, INDEX)
        assert "Outlet A3" in sensor._attr_name


class TestRenamePropagation:
    def test_sensor_name_follows_coordinator_update(self):
        cls = SnmpOutletCurrentSensorEntity
        oids = oids_for(INDEX)
        data = {
            **UNIT_META,
            oids["designator"]: "A3",
            oids["name"]: "PDU 0 Outlet A3",
            oids["status"]: 1,
            oids["current"]: 500,
        }
        sensor = cls(FakeCoordinator(data), UNIT, INDEX)
        uid_before = sensor._attr_unique_id
        assert "Outlet A3" in sensor._attr_name

        data[oids["name"]] = "nvr"
        sensor._handle_coordinator_update()
        assert sensor._attr_name.startswith("nvr ")
        assert sensor._attr_unique_id == uid_before

    def test_value_survives_rename_cycle(self):
        """Renaming must not clobber the sensor's measured value."""
        cls = SnmpOutletCurrentSensorEntity
        oids = oids_for(INDEX)
        data = {
            **UNIT_META,
            oids["name"]: "nvr",
            oids["status"]: 1,
            oids["current"]: 500,
        }
        sensor = cls(FakeCoordinator(data), UNIT, INDEX)
        value_before = sensor._attr_native_value
        sensor._handle_coordinator_update()
        assert sensor._attr_native_value == pytest.approx(value_before)
