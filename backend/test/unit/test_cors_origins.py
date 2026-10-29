"""Orígenes CORS configurables y sin localhost en producción."""

import pytest

from main import DEV_ORIGINS, get_allowed_origins


def test_production_uses_only_configured_origins():
    origins = get_allowed_origins("https://app.example.com, https://admin.example.com/", False)

    assert origins == ["https://app.example.com", "https://admin.example.com"]


def test_production_without_configuration_allows_no_cross_origin():
    assert get_allowed_origins("", False) == []


def test_development_keeps_localhost():
    assert get_allowed_origins("https://app.example.com", True) == DEV_ORIGINS + [
        "https://app.example.com"
    ]


def test_wildcard_with_credentials_is_rejected():
    with pytest.raises(ValueError):
        get_allowed_origins("*", False)
