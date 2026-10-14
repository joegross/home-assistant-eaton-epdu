"""Integration-suite conftest: uses the real HA test harness.

No stubbing here — pytest-homeassistant-custom-component provides the
hass fixture and the real homeassistant package. Pytest plugin autoload
is disabled via PYTEST_DISABLE_PLUGIN_AUTOLOAD, so the harness plugin
must be enabled explicitly (see pytest.ini testpaths/overrides or -p).
"""
