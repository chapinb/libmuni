"""Fail if the packaged version and the changelog disagree.

Enforces the release discipline in CLAUDE.md: ``pyproject.toml``'s version
reflects the most recently *released* (dated) entry in ``CHANGELOG.md``, so a
version bump and its dated changelog entry always land together. Before the
first release there are no dated entries; the only requirement then is that an
``## [Unreleased]`` section exists to collect pending changes.

Run as a pre-commit hook (see ``.pre-commit-config.yaml``); exits non-zero with
a one-line explanation on a mismatch.
"""

import re
import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _ROOT / "pyproject.toml"
_CHANGELOG = _ROOT / "CHANGELOG.md"

_DATED_HEADING = re.compile(
    r"^##\s*\[(?P<version>\d+\.\d+\.\d+)\]\s*-\s*\d{4}-\d{2}-\d{2}", re.MULTILINE
)
_UNRELEASED_HEADING = re.compile(r"^##\s*\[Unreleased\]", re.MULTILINE | re.IGNORECASE)


def latest_released_version(changelog: str) -> str | None:
    """Return the version of the topmost dated ``## [x.y.z] - date`` heading, if any."""
    match = _DATED_HEADING.search(changelog)
    return match.group("version") if match else None


def evaluate(version: str, changelog: str) -> str | None:
    """Return an error message if ``version`` and ``changelog`` disagree, else ``None``.

    Args:
        version: The version declared in ``pyproject.toml``.
        changelog: The full text of ``CHANGELOG.md``.

    Returns:
        A human-readable problem description, or ``None`` when consistent.
    """
    released = latest_released_version(changelog)
    if released is None:
        if not _UNRELEASED_HEADING.search(changelog):
            return "CHANGELOG.md has no '## [Unreleased]' section to collect pending changes"
        return None
    if released != version:
        return (
            f"pyproject version {version!r} does not match the latest released "
            f"CHANGELOG heading {released!r}; bump the version and date its changelog "
            "entry in the same commit"
        )
    return None


def main() -> int:
    """Check the repo's files and report any inconsistency for the pre-commit hook."""
    version = str(tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["version"])
    error = evaluate(version, _CHANGELOG.read_text(encoding="utf-8"))
    if error:
        print(f"changelog-version: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
