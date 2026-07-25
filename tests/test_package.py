"""Smoke tests for the package scaffold."""

import aet


def test_version():
    assert aet.__version__


def test_subpackages_import():
    import aet.circuits
    import aet.maintenance
    import aet.photometrics
    import aet.reporting  # noqa: F401
