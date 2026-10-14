"""Repo-root conftest for the eaton_epdu test suite.

The lean unit suite under tests/unit/ stubs the Home Assistant module
graph itself (see tests/unit/conftest.py) and must not also load the
pytest-homeassistant-custom-component plugin, whose autouse fixtures
expect the real HA packages. The plugin registers itself via a pytest11
entry point ( Loads before ini addopts), so it is blocked here at the
earliest conftest load stage.
"""


def pytest_cmdline_main(config):
    return None  # unused; placeholder so this file always imports cleanly


collect_ignore_glob = []  # kept minimal; no directories excluded by default