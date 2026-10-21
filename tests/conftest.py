"""Session plumbing: the regression runs' wall times, printed at the end of the session."""

from __future__ import annotations

import pytest

from mobcal import fortran

_RUN_TIMES = pytest.StashKey[dict[str, float]]()


@pytest.fixture(scope="session")
def run_times(pytestconfig) -> dict[str, float]:
    return pytestconfig.stash.setdefault(_RUN_TIMES, {})


def pytest_terminal_summary(terminalreporter, config):
    times = config.stash.get(_RUN_TIMES, {})
    if not times:
        return
    terminalreporter.section("choline run times")
    terminalreporter.write_line(fortran.describe())
    for gas, s in times.items():
        terminalreporter.write_line(f"{gas}: {s:.1f} s wall, binary alone")
