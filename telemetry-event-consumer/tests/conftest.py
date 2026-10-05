"""Shared pytest setup for this component's test suite.

Makes consume_telemetry_events.py importable (it's a standalone script, not an installed
package) and stubs out `pyodbc` when the real package can't be imported -- most dev machines and
CI runners won't have a Microsoft ODBC driver installed at the OS level, and nothing under test
actually needs real ODBC behavior, only the module to exist. Same pattern as
telemetry-event-generator/tests/conftest.py -- see that component's CLAUDE.md for why this
shape was chosen; it's meant to generalize across the repo, not be reinvented per component.
"""
import sys
import types
from pathlib import Path

COMPONENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COMPONENT_ROOT))

try:
    import pyodbc  # noqa: F401
except ImportError:
    fake_pyodbc = types.ModuleType("pyodbc")
    fake_pyodbc.Error = type("Error", (Exception,), {})
    fake_pyodbc.Cursor = object
    fake_pyodbc.Connection = object

    def _unexpected_connect(*args, **kwargs):
        raise AssertionError(
            "fake pyodbc.connect() called without being monkeypatched for this test"
        )

    fake_pyodbc.connect = _unexpected_connect
    sys.modules["pyodbc"] = fake_pyodbc
