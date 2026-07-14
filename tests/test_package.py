"""Scaffold acceptance: the package imports and declares its version."""

from importlib.metadata import version

import libcivicclerk


def test_package_exposes_version():
    # Single-sourced from pyproject.toml via distribution metadata.
    assert libcivicclerk.__version__ == version("libcivicclerk")
