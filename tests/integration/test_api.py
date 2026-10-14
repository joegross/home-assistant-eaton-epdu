"""SnmpApi layer tests against the mocked pysnmp boundary.

Covers: get (single, unknown-OID retry, transport error), cast chains,
get_bulk (walk shape, count clamp, batching, errors), get_bulk_auto,
set (write-credential selection, type mapping, error paths).
"""

from __future__ import annotations

import pytest

import custom_components.eaton_epdu.api as api_mod
from contextlib import ExitStack
from custom_components.eaton_epdu.api import SnmpApi
from tests.integration.snmp_fake import (
    identity_table,
    live_pdu_table,
    make_fake,
    patched_snmp_api,
    default_walker,
)

BASE = "1.3.6.1.4.1.534.6.6.7"


def enter_all(ctxs) -> ExitStack:
    """Enter every patch context on one stack (use as `with enter_all(ctxs):`)."""
    stack = ExitStack()
    for c in ctxs:
        stack.enter_context(c)
    return stack


class TestGet:
    async def test_get_returns_cast_values(self):
        api, ctxs = patched_snmp_api(live_pdu_table())
        with enter_all(ctxs):
            result = await api.get([f"{BASE}.1.2.1.3.0", f"{BASE}.1.2.1.22.0"])
        assert result[f"{BASE}.1.2.1.3.0"] == "EMA112-10"
        assert result[f"{BASE}.1.2.1.22.0"] == 16

    async def test_get_unknown_oid_returns_empty(self):
        api, ctxs = patched_snmp_api({})
        with enter_all(ctxs):
            result = await api.get([f"{BASE}.9.9.9.9"])
        assert result == {}

    async def test_get_partial_known_set_drops_unknown(self):
        table = {f"{BASE}.1.1.0": "0,1"}
        api, ctxs = patched_snmp_api(table)
        with enter_all(ctxs):
            result = await api.get([f"{BASE}.1.1.0", f"{BASE}.9.9.9.9"])
        # unknown OID popped (error_index retry), second pass resolves
        assert result == {f"{BASE}.1.1.0": "0,1"}

    async def test_get_transport_error_raises(self):
        api, ctxs = patched_snmp_api(identity_table())

        async def timeout_get(*args):
            return ("timeout: no response", None, 0, ())

        orig = api_mod.hlapi.get_cmd
        api_mod.hlapi.get_cmd = timeout_get
        try:
            with pytest.raises(RuntimeError, match="Got SNMP error"):
                await api.get([f"{BASE}.1.1.0"])
        finally:
            api_mod.hlapi.get_cmd = orig


class TestCast:
    @pytest.mark.parametrize(
        ("raw", "want"),
        [
            (16, 16),
            ("16", 16),
            ("16.5", 16.5),
            ("EMA112-10", "EMA112-10"),
            ("2026-04-29", "2026-04-29"),
        ],
    )
    def test_cast(self, raw, want):
        assert SnmpApi.cast(raw) == want
        assert type(SnmpApi.cast(raw)) is type(want)

    def test_cast_float_input_becomes_int(self):
        """Documented gotcha: cast() prefers int, so 16.5 -> 16."""
        assert SnmpApi.cast(16.5) == 16


class TestGetBulk:
    async def test_bulk_walks_rows_with_count_clamp(self):
        table = live_pdu_table()
        api, ctxs = patched_snmp_api(table)
        walk_oid = f"{BASE}.6.1.1.2.0."
        with enter_all(ctxs):
            rows = await api.get_bulk([walk_oid], 16)
        assert len(rows) == 16
        assert rows[0][walk_oid + "1"] == 1  # cast() turns "1" into int
        assert rows[15][walk_oid + "16"] == 16

    async def test_bulk_count_zero_returns_empty(self):
        api, ctxs = patched_snmp_api(identity_table())
        with enter_all(ctxs):
            assert await api.get_bulk([f"{BASE}.6.1.1.2.0."], 0) == []

    async def test_bulk_batches_beyond_max_repetitions(self):
        """count > 4 forces multiple bulk_cmd calls (batching loop)."""
        calls = []
        walker = default_walker({f"{BASE}.1.1.0.{i}": i for i in range(1, 11)})
        _, fake_bulk, _, _, _ = make_fake({}, walker)

        async def counting_bulk(*args):
            calls.append(args[5])
            return await fake_bulk(*args)

        api, ctxs = patched_snmp_api({})
        with enter_all(ctxs):
            # installed INSIDE the context: entering contexts replaces
            # hlapi.bulk_cmd, so the counting wrapper goes in second
            orig = api_mod.hlapi.bulk_cmd
            api_mod.hlapi.bulk_cmd = counting_bulk
            try:
                rows = await api.get_bulk([f"{BASE}.1.1.0."], 10)
            finally:
                api_mod.hlapi.bulk_cmd = orig
        assert len(rows) == 10
        assert all(c <= 4 for c in calls)
        assert len(calls) == 3  # batches 4+4+2

    async def test_bulk_error_raises(self):
        api, ctxs = patched_snmp_api(identity_table())

        async def err_bulk(*args):
            return ("genError", None, 0, [])

        with enter_all(ctxs):
            orig = api_mod.hlapi.bulk_cmd
            api_mod.hlapi.bulk_cmd = err_bulk
            try:
                with pytest.raises(RuntimeError, match="Got SNMP error"):
                    await api.get_bulk([f"{BASE}.1.1.0."], 4)
            finally:
                api_mod.hlapi.bulk_cmd = orig


class TestGetBulkAuto:
    async def test_auto_resolves_count_oid(self):
        table = identity_table()
        table[f"{BASE}.1.2.1.22.0"] = 2
        walker = default_walker(
            {f"{BASE}.6.1.1.2.0.1": "A1", f"{BASE}.6.1.1.2.0.2": "A2"}
        )
        api, ctxs = patched_snmp_api(table, walker)
        with enter_all(ctxs):
            rows = await api.get_bulk_auto(
                [f"{BASE}.6.1.1.2.0."], f"{BASE}.1.2.1.22.0"
            )
        assert len(rows) == 2
        assert rows[0][f"{BASE}.6.1.1.2.0.1"] == "A1"
        assert rows[1][f"{BASE}.6.1.1.2.0.2"] == "A2"


class TestSet:
    async def test_set_records_binding_and_uses_write_credentials(self):
        sets: dict = {}
        _, _, fake_set, _, _ = make_fake({}, sets=sets)
        api, ctxs = patched_snmp_api({})
        api.__dict__["_credentials"] = "read-cred"
        api.__dict__["_credentials_write"] = "write-cred"
        seen = {}

        async def spy_set(*args):
            seen["credentials"] = args[1]
            return await fake_set(*args)

        with enter_all(ctxs):
            # spy must be installed INSIDE the context: entering contexts
            # replaces hlapi.set_cmd with the fake, so patch order matters
            orig = api_mod.hlapi.set_cmd
            api_mod.hlapi.set_cmd = spy_set
            try:
                ok = await api.set(f"{BASE}.6.6.1.4.0.3", 1, "Integer")
            finally:
                api_mod.hlapi.set_cmd = orig
        assert ok is True
        assert seen["credentials"] == "write-cred"
        assert sets[f"{BASE}.6.6.1.4.0.3"] == 1

    async def test_set_falls_back_to_read_credentials(self):
        sets: dict = {}
        _, _, fake_set, _, _ = make_fake({}, sets=sets)
        api, ctxs = patched_snmp_api({})
        api.__dict__["_credentials"] = "read-cred"
        seen = {}

        async def spy_set(*args):
            seen["credentials"] = args[1]
            return await fake_set(*args)

        with enter_all(ctxs):
            orig = api_mod.hlapi.set_cmd
            api_mod.hlapi.set_cmd = spy_set
            try:
                await api.set(f"{BASE}.6.6.1.4.0.3", 1, "Integer")
            finally:
                api_mod.hlapi.set_cmd = orig
        assert seen["credentials"] == "read-cred"

    async def test_set_unsupported_type_raises(self):
        api, ctxs = patched_snmp_api({})
        with enter_all(ctxs), pytest.raises(ValueError, match="Unsupported SNMP type"):
            await api.set(f"{BASE}.1.1.0", "x", "Counter64")

    async def test_set_error_status_raises(self):
        api, ctxs = patched_snmp_api({})

        class FakeStatus:
            def prettyPrint(self):
                return "authorizationError"

        async def err_set(*args):
            return ("", FakeStatus(), 1, ())

        with enter_all(ctxs):
            orig = api_mod.hlapi.set_cmd
            api_mod.hlapi.set_cmd = err_set
            try:
                with pytest.raises(RuntimeError, match="authorizationError"):
                    await api.set(f"{BASE}.6.6.1.4.0.3", 1, "Integer")
            finally:
                api_mod.hlapi.set_cmd = orig

    async def test_set_error_indication_raises(self):
        api, ctxs = patched_snmp_api({})

        async def err_set(*args):
            return ("timeout", None, 0, ())

        with enter_all(ctxs):
            orig = api_mod.hlapi.set_cmd
            api_mod.hlapi.set_cmd = err_set
            try:
                with pytest.raises(RuntimeError, match="SNMP set error"):
                    await api.set(f"{BASE}.6.6.1.4.0.3", 1, "Integer")
            finally:
                api_mod.hlapi.set_cmd = orig
