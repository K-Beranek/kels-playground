"""Shared pytest setup for this component's test suite.

Makes generate_telemetry_events.py importable (it's a standalone script, not an installed
package) and stubs out `pyodbc` when the real package can't be imported -- most dev machines
and CI runners won't have a Microsoft ODBC driver installed at the OS level, and none of the
logic under test actually needs real ODBC behaviour (see generate_telemetry_events.py's own
try/except ImportError for why pyodbc needs that driver at all). kafka-python, by contrast, is
a pure-Python package with no OS-level dependency, so it's a normal installed dependency here
(see requirements-dev.txt) rather than something that needs stubbing.
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
