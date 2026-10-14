"""Definition of base Eaton ePDU Entity."""

from __future__ import annotations

import re

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    SNMP_OID_OUTLETS_DESIGNATOR,
    SNMP_OID_OUTLETS_NAME,
    SNMP_OID_UNITS_DEVICE_NAME,
    SNMP_OID_UNITS_FIRMWARE_VERSION,
    SNMP_OID_UNITS_PART_NUMBER,
    SNMP_OID_UNITS_PRODUCT_NAME,
    SNMP_OID_UNITS_SERIAL_NUMBER,
)
from .coordinator import SnmpCoordinator


class SnmpEntity(CoordinatorEntity[SnmpCoordinator]):
    """Base class for Eaton ePDU entities."""

    def __init__(self, coordinator: SnmpCoordinator, unit: str) -> None:
        """Initialize a Eaton ePDU entity."""
        super().__init__(coordinator)
        self._unit = unit

    def get_unit_data(self, oid: str, default=None):
        """Fetch data from coordinator for current unit."""
        return self.coordinator.data.get(oid.replace("unit", self._unit), default)

    def get_outlet_label(self, index: str) -> str:
        """Return a display label for an outlet.

        Preference order:

        1. The outlet name set by the user on the ePDU (outletName), when it
           is not a factory default like "PDU 0 Outlet A3".
        2. The outlet designator (physical label, e.g. "A3") for ePDUs whose
           names have not been customized.
        3. The outlet index as a last resort.
        """
        name = self.get_outlet_name(index)
        if name is not None:
            return name

        designator = self.get_outlet_designator(index)
        if designator not in (None, ""):
            return f"Outlet {designator}"

        return f"Outlet {index}"

    def get_outlet_name(self, index: str) -> str | None:
        """Return the user-defined outlet name, or None when not customized."""
        name_oid = SNMP_OID_OUTLETS_NAME.replace("unit", self._unit).replace(
            "index", index
        )
        name = self.coordinator.data.get(name_oid)
        if name in (None, ""):
            return None
        name = str(name).strip()
        if name == "":
            return None
        if re.fullmatch(r"PDU \d+ Outlet [A-Za-z]?\d+[a-z]?", name):
            # Factory default, not a user-provided name.
            return None
        if name.casefold().startswith("outlet "):
            return name
        return name

    def get_outlet_designator(self, index: str) -> str | None:
        """Return the outlet designator (physical label), e.g. "A3"."""
        designator_oid = SNMP_OID_OUTLETS_DESIGNATOR.replace(
            "unit", self._unit
        ).replace("index", index)
        designator = self.get_unit_data(designator_oid)
        return designator if designator not in (None, "") else None

    @property
    def identifier(self):
        """Return the device identifier."""
        return self.get_unit_data(
            SNMP_OID_UNITS_SERIAL_NUMBER,
            self.get_unit_data(
                SNMP_OID_UNITS_DEVICE_NAME,
                self.get_unit_data(
                    SNMP_OID_UNITS_PART_NUMBER,
                    self.get_unit_data(SNMP_OID_UNITS_PRODUCT_NAME),
                ),
            ),
        )

    @property
    def device_info(self):
        """Return the device_info of the device."""
        model = self.get_unit_data(SNMP_OID_UNITS_PRODUCT_NAME)
        name = self.get_unit_data(SNMP_OID_UNITS_DEVICE_NAME)
        if name:
            model = f"{self.get_unit_data(SNMP_OID_UNITS_PART_NUMBER)} {model}"
        else:
            name = self.get_unit_data(SNMP_OID_UNITS_PART_NUMBER)

        return DeviceInfo(
            identifiers={(DOMAIN, self.identifier)},
            manufacturer=MANUFACTURER,
            model=model,
            name=name,
            serial_number=self.get_unit_data(SNMP_OID_UNITS_SERIAL_NUMBER),
            sw_version=self.get_unit_data(SNMP_OID_UNITS_FIRMWARE_VERSION),
        )
