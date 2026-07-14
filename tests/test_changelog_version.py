"""Guard the changelog/version consistency rule the release hook enforces."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_changelog_version.py"
_spec = importlib.util.spec_from_file_location("check_changelog_version", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check_changelog_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_changelog_version)

evaluate = check_changelog_version.evaluate

_RELEASED = """# Changelog

## [Unreleased]

## [0.2.0] - 2026-07-14

### Added
- something

## [0.1.0] - 2026-06-01
"""

_PRE_RELEASE = """# Changelog

## [Unreleased]

### Added
- initial release
"""


def test_matching_released_version_passes():
    assert evaluate("0.2.0", _RELEASED) is None


def test_mismatched_released_version_fails():
    error = evaluate("0.3.0", _RELEASED)
    assert error is not None
    assert "0.3.0" in error
    assert "0.2.0" in error


def test_pre_first_release_passes_with_unreleased_section():
    assert evaluate("0.1.0", _PRE_RELEASE) is None


def test_pre_first_release_fails_without_unreleased_section():
    error = evaluate("0.1.0", "# Changelog\n\nnothing here\n")
    assert error is not None
    assert "Unreleased" in error


def test_latest_released_version_takes_the_topmost_dated_heading():
    assert check_changelog_version.latest_released_version(_RELEASED) == "0.2.0"
