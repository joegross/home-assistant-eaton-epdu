"""Repo-root conftest for the eaton_epdu test suite.

The lean unit suite under tests/unit/ stubs the Home Assistant module
graph itself (see tests/unit/conftest.py) and must not also load the
pytest-homeassistant-custom-component plugin, whose autouse fixtures
expect the real HA packages. The plugin registers itself via a pytest11
entry point and loads before ini addopts are applied; run the unit
suite with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 (CI's test.yaml does).
"""