"""Test configuration providing minimal stubs for optional dependencies."""

import os
import sys
import types


def _ensure_stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules.setdefault(name, module)
    return module


# Provide very small stubs so that strategy modules can be imported without
# Provide very small stubs so that strategy modules can be imported without
# heavy third-party dependencies. These stubs are sufficient because the tests
# only exercise object construction and never call functions that rely on these
# libraries.

# Ensure the repository root is on the import path for tests executed from the
# ``tests`` directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

pandas = _ensure_stub("pandas")
setattr(pandas, "DataFrame", type("DataFrame", (), {}))
setattr(pandas, "Series", type("Series", (), {}))

_ensure_stub("numpy")
_ensure_stub("requests")

