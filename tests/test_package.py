"""Scaffold acceptance: the package imports and declares its version."""

from importlib.metadata import version

import libmuni


def test_package_exposes_version():
    # Single-sourced from pyproject.toml via distribution metadata.
    assert libmuni.__version__ == version("libmuni")
