"""Tenant slice: the subdomain is validated before it reaches the API host.

The tenant is interpolated into ``https://{tenant}.api.civicclerk.com``, so a
value carrying a URL-significant character could redirect requests to another
host. Construction rejects anything that is not a single DNS label.
"""

import pytest

from libcivicclerk import CivicClerkClient


@pytest.mark.parametrize(
    "tenant",
    [
        "exampletown",
        "example-town",
        "a",
        "abc123",
        "1example",
        "a" * 63,
    ],
)
def test_valid_subdomain_labels_are_accepted(tenant: str):
    with CivicClerkClient(tenant) as client:
        assert client.tenant == tenant
        assert client.base_url == f"https://{tenant}.api.civicclerk.com/v1"


@pytest.mark.parametrize(
    "tenant",
    [
        "",
        "evil.com/",
        "evil.com#",
        "evil.com?",
        "a@evil.com",
        "example.town",
        "-example",
        "example-",
        "exam ple",
        "a" * 64,
    ],
)
def test_hostile_or_malformed_tenants_are_rejected(tenant: str):
    with pytest.raises(ValueError, match="invalid tenant"):
        CivicClerkClient(tenant)
