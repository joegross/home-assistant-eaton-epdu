"""Mock SNMP transport at the pysnmp hlapi boundary.

Replaces get_cmd/bulk_cmd/set_cmd (and ObjectType/ObjectIdentity, which
normally require live MIB resolution) inside the
custom_components.eaton_epdu.api module namespace — no network, no real
agent. Value shapes mirror the live EMA112-10 (recorded via snmpwalk).
"""

from __future__ import annotations

from unittest.mock import patch

from custom_components.eaton_epdu.api import SnmpApi

BASE = "1.3.6.1.4.1.534.6.6.7"
SNMP_OID_UNITS = f"{BASE}.1.1.0"


class FakeVarBind:
    """(name, value) pair as get/bulk/set_cmds yield."""

    def __init__(self, name: str, value):
        self._name = name
        self._value = value

    def __getitem__(self, key):
        return self._name if key == 0 else self._value

    def __iter__(self):
        return iter((self._name, self._value))

    def __str__(self):
        return self._name


class FakeObjectIdentity:
    def __init__(self, oid):
        self.oid = str(oid)

    def __str__(self):
        return self.oid


class FakeObjectType:
    """Tracks (identity, value) without MIB resolution."""

    def __init__(self, identity, value=None):
        self.identity = identity
        self.value = value

    def __getitem__(self, key):
        if key == 0:
            return self.identity
        return self.value

    def __str__(self):
        return str(self.identity)


def _oid_of(obj) -> str:
    """Extract the numeric OID from any object the api may pass along.

    The batching loop in get_bulk re-passes previous var_binds as the
    next request's object types — accept FakeObjectType, FakeVarBind,
    or plain strings.
    """
    if isinstance(obj, FakeObjectType):
        return str(obj.identity)
    if isinstance(obj, FakeVarBind):
        return obj._name
    return str(obj)


def make_fake(api_table: dict, walker=None, sets=None):
    """Build (get_cmd, bulk_cmd, set_cmd, ObjectType, ObjectIdentity).

    get_cmd: unknown OIDs surface via error_index (noSuchName-like).
    bulk_cmd: walks via default_walker (seed-honoring) when no walker given.
    set_cmd: records (oid, value) into `sets` dict, echoes success.
    """
    if walker is None:
        walker = default_walker(api_table)

    async def fake_get_cmd(*args):
        var_binds = []
        for pos, ot in enumerate(args[4:], start=1):
            oid = _oid_of(ot)
            if oid not in api_table:
                return ("", None, pos, [])
            var_binds.append(FakeVarBind(oid, api_table[oid]))
        return ("", None, 0, tuple(var_binds))

    async def fake_bulk_cmd(*args):
        max_rep = args[5]
        flat = []
        for ot in args[6:]:
            flat.extend(walker(_oid_of(ot), max_rep))
        return ("", None, 0, flat)

    async def fake_set_cmd(*args):
        ot = args[4]
        if sets is not None:
            sets[str(ot.identity)] = ot.value
        return ("", None, 0, (FakeVarBind(str(ot.identity), ot.value),))

    return fake_get_cmd, fake_bulk_cmd, fake_set_cmd, FakeObjectType, FakeObjectIdentity


def patched_snmp_api(api_table: dict, walker=None):
    """(SnmpApi, contexts) — enter all contexts around calls in tests."""
    fake_get, fake_bulk, fake_set, obj_type, obj_id = make_fake(
        api_table, walker
    )
    api = SnmpApi(snmpEngine=object())
    # configured state as setup() would leave it for v1 / no-write
    api.__dict__["_credentials"] = "read-cred"
    api.__dict__["_credentials_write"] = None
    api.__dict__["_target"] = "target"
    contexts = (
        patch("custom_components.eaton_epdu.api.hlapi.get_cmd", fake_get),
        patch("custom_components.eaton_epdu.api.hlapi.bulk_cmd", fake_bulk),
        patch("custom_components.eaton_epdu.api.hlapi.set_cmd", fake_set),
        patch("custom_components.eaton_epdu.api.hlapi.ObjectType", obj_type),
        patch("custom_components.eaton_epdu.api.hlapi.ObjectIdentity", obj_id),
    )
    return api, contexts


def default_walker(api_table: dict):
    """Walk rows lexicographically from a seed OID.

    Honors mid-table re-seeds: a seed ending in row index N resumes at
    N+1 (mirroring real pysnmp bulk_cmd continue-from behavior, which
    get_bulk relies on for its batching loop).
    """

    def walk(oid: str, count: int) -> list[FakeVarBind]:
        seed = str(oid)
        if seed.endswith("."):
            first = 1
            prefix = seed
        else:
            # re-seeded mid-table: '...0.4' -> resume at .5
            stem, _, tail = seed.rpartition(".")
            if tail.isdigit():
                first = int(tail) + 1
                prefix = stem + "."
            else:
                first = 1
                prefix = seed
        return [
            FakeVarBind(f"{prefix}{i}", api_table.get(f"{prefix}{i}", i))
            for i in range(first, first + count)
        ]

    return walk


def identity_table() -> dict:
    return {SNMP_OID_UNITS: "0,1"}


def live_pdu_table() -> dict:
    """OID->value table recorded from the live EMA112-10 (snmpwalk)."""
    table = {
        SNMP_OID_UNITS: "0,1",
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
        f"{BASE}.1.2.1.20.0": 2,
        f"{BASE}.1.2.1.20.1": 2,
        f"{BASE}.1.2.1.22.0": 16,
        f"{BASE}.1.2.1.22.1": 16,
        f"{BASE}.3.1.1.10.0.": "L1",
        f"{BASE}.3.1.1.10.1.": "L1",
        f"{BASE}.3.2.1.3.0.": 120000,
        f"{BASE}.3.3.1.4.0.": 1879,
        f"{BASE}.3.4.1.4.0.": 225,
        f"{BASE}.3.4.1.5.0.": 1_000_000,
        f"{BASE}.3.4.1.7.0.": 985,
    }
    # outlet index table (walk target in tests)
    for idx in range(1, 17):
        table[f"{BASE}.6.1.1.2.0.{idx}"] = f"{idx}"
    for unit in ("0", "1"):
        for idx in range(1, 17):
            table[f"{BASE}.6.1.1.3.{unit}.{idx}"] = (
                "nvr" if (unit == "0" and idx == 3) else f"PDU {unit} Outlet A{idx}"
            )
            table[f"{BASE}.6.1.1.6.{unit}.{idx}"] = f"A{idx}"
            table[f"{BASE}.6.6.1.2.{unit}.{idx}"] = 1
            table[f"{BASE}.6.4.1.3.{unit}.{idx}"] = 100
            table[f"{BASE}.6.5.1.6.{unit}.{idx}"] = 950
            table[f"{BASE}.6.5.1.3.{unit}.{idx}"] = 12
            table[f"{BASE}.6.5.1.4.{unit}.{idx}"] = 5000
    return table
