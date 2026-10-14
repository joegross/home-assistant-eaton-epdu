"""Shared pytest fixtures for the standalone eaton_epdu test suite.

Stubs the Home Assistant / pysnmp module graph so the component imports
on a bare interpreter, then puts custom_components/ on sys.path.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # .../home-assistant-eaton-epdu
COMPONENT_DIR = REPO / "custom_components"


def _module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _install_stubs() -> None:
    ha = _module("homeassistant")
    helpers = _module("homeassistant.helpers")
    comp_mod = _module("homeassistant.components")
    comp_snmp = _module("homeassistant.components.snmp")

    class DeviceInfo(dict):
        def __init__(self, **kw):
            super().__init__(**kw)

    class CoordinatorEntity:
        """Minimum CoordinatorEntity: stores coordinator, subscriptable."""

        def __init__(self, coordinator):
            self.coordinator = coordinator

        def __class_getitem__(cls, item):
            return cls

        def _handle_coordinator_update(self) -> None:
            pass

        def async_write_ha_state(self) -> None:
            pass

    class _Platform:
        SENSOR = "sensor"
        SWITCH = "switch"

    entity_mod = _module(
        "homeassistant.helpers.entity", DeviceInfo=DeviceInfo
    )
    uc_mod = _module(
        "homeassistant.helpers.update_coordinator",
        CoordinatorEntity=CoordinatorEntity,
        DataUpdateCoordinator=type(
            "DataUpdateCoordinator",
            (),
            {"__init__": lambda self, *a, **kw: None},
        ),
        UpdateFailed=type("UpdateFailed", (Exception,), {}),
    )
    core_mod = _module(
        "homeassistant.core",
        callback=lambda f: f,
        HomeAssistant=object,
    )
    const_mod = _module("homeassistant.const", Platform=_Platform)
    core_mod = _module(
        "homeassistant.core",
        callback=lambda f: f,
        HomeAssistant=object,
    )
    # Units used by sensor.py imports (enum-members accessed as X.AMPERE etc.)
    class _UnitStr(str):
        def __getattr__(self, name):
            return _UnitStr(name)

    for attr in (
        "UnitOfElectricCurrent",
        "UnitOfElectricPotential",
        "UnitOfEnergy",
        "UnitOfPower",
    ):
        setattr(const_mod, attr, _UnitStr(attr))
    config_entries = _module(
        "homeassistant.config_entries", ConfigEntry=object
    )
    dr_mod = _module(
        "homeassistant.helpers.device_registry", DeviceEntry=object
    )
    ep_mod = _module(
        "homeassistant.helpers.entity_platform",
        AddEntitiesCallback=object,
    )

    sys.modules.update(
        {
            "homeassistant": ha,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.entity": entity_mod,
            "homeassistant.helpers.update_coordinator": uc_mod,
            "homeassistant.helpers.device_registry": dr_mod,
            "homeassistant.helpers.entity_platform": ep_mod,
            "homeassistant.core": core_mod,
            "homeassistant.const": const_mod,
            "homeassistant.config_entries": config_entries,
            "homeassistant.components": comp_mod,
            "homeassistant.components.snmp": comp_snmp,
            "homeassistant.components.snmp.util": _module(
                "homeassistant.components.snmp.util",
                async_get_snmp_engine=lambda *a, **kw: None,
            ),
            "homeassistant.components.switch": _module(
                "homeassistant.components.switch", SwitchEntity=object
            ),
        }
    )
    # Sensor enums with members used at class-definition time
    sensor_mod = _module("homeassistant.components.sensor")
    sensor_mod.SensorEntity = object

    class _StrEnum(str):
        def __getattr__(cls, name):
            return cls.__name__ + "." + name

    class _Enum:
        def __init__(self, name):
            self.__name = name
            self.MEASUREMENT = "measurement"
            self.TOTAL_INCREASING = "total_increasing"
            self.CURRENT = "current"
            self.POWER = "power"
            self.POWER_FACTOR = "power_factor"
            self.VOLTAGE = "voltage"
            self.ENERGY = "energy"

        def __getattr__(self, name):
            return name.casefold()

    for enum_name in ("SensorDeviceClass", "SensorStateClass"):
        setattr(sensor_mod, enum_name, _Enum(enum_name))
    sys.modules["homeassistant.components.sensor"] = sensor_mod

    # pysnmp: imported by api.py; exercised nowhere in this suite
    pysnmp = _module("pysnmp")
    sys.modules["pysnmp"] = pysnmp
    sys.modules["pysnmp.error"] = _module(
        "pysnmp.error", PySnmpError=type("PySnmpError", (Exception,), {})
    )
    hlapi = _module("pysnmp.hlapi.asyncio")
    sys.modules["pysnmp.hlapi"] = _module("pysnmp.hlapi")
    sys.modules["pysnmp.hlapi.asyncio"] = hlapi
    for attr in (
        "CommunityData",
        "ContextData",
        "ObjectIdentity",
        "ObjectType",
        "UdpTransportTarget",
        "Udp6TransportTarget",
        "UsmUserData",
        "bulk_cmd",
        "get_cmd",
        "set_cmd",
        "SnmpEngine",
    ):
        setattr(hlapi, attr, object)
    for attr in (
        "USM_AUTH_NONE",
        "USM_PRIV_NONE",
        "USM_AUTH_HMAC96_MD5",
        "USM_AUTH_HMAC96_SHA",
        "USM_AUTH_HMAC128_SHA224",
        "USM_AUTH_HMAC192_SHA256",
        "USM_AUTH_HMAC256_SHA384",
        "USM_AUTH_HMAC384_SHA512",
        "USM_PRIV_CBC56_DES",
        "USM_PRIV_CBC168_3DES",
        "USM_PRIV_CFB128_AES",
        "USM_PRIV_CFB192_AES",
        "USM_PRIV_CFB192_AES_BLUMENTHAL",
        "USM_PRIV_CFB256_AES",
        "USM_PRIV_CFB256_AES_BLUMENTHAL",
    ):
        setattr(hlapi, attr, attr)
    hlapi.hlapi = hlapi
    sys.modules["pysnmp.proto"] = _module("pysnmp.proto")
    sys.modules["pysnmp.proto.rfc1902"] = _module(
        "pysnmp.proto.rfc1902", Integer=int, OctetString=str
    )


_install_stubs()
if str(COMPONENT_DIR) not in sys.path:
    sys.path.insert(0, str(COMPONENT_DIR))
