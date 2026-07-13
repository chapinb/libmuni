"""Scaffold acceptance: the package imports and declares its version."""

import libcivicclerk


def test_package_exposes_version():
    assert libcivicclerk.__version__ == "0.1.0"
