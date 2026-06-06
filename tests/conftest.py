"""Shared pytest fixtures and test isolation.

STOPGAP. The library currently keeps a process-wide symbol-library cache
singleton (``kicad_sch_api.library.cache._global_cache``). Tests that mutate it
-- e.g. by calling ``add_library_path()`` to register a local ``.kicad_sym`` --
leak that state into every later test, so a subsequent bare
``components.add("Device:R")`` fails with ``LibraryError``. There was previously
no conftest at all, which is why ~90 unit tests failed only in full-suite
(order-dependent) runs while passing in isolation.

The autouse fixture below resets the singleton around every test. Discovery is
backed by a persistent on-disk index, so re-discovering per test is cheap (the
suite's wall time is dominated by real schematic I/O, not discovery).

This whole file becomes unnecessary once the symbol library is an explicit,
instance-scoped dependency instead of a global -- see FORK_MAINTENANCE.md P0.
"""

import pytest

from kicad_sch_api.library import cache as _cache


@pytest.fixture(autouse=True)
def _reset_symbol_cache():
    """Give every test a fresh global symbol cache (undo any test's mutations)."""
    _cache.set_symbol_cache(None)
    try:
        yield
    finally:
        _cache.set_symbol_cache(None)
