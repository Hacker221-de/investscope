import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("entry", [
    "*", "", "   ", "http://example.com", "https://example.com", "example.com:8000",
    "[::1]", "example.com/path", " example.com", "example.com ", "user@example.com",
    "example.com?query", "example.com#fragment", "example..com", "*.example.com",
    "::1%lo0", "[::1]:8000", "127.0.0.1:8000", "localhost\n", "exa_mple.com",
])
def test_invalid_trusted_host_is_configuration_error(entry):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, trusted_hosts=["localhost", entry])


def test_trusted_host_defaults_and_environment_override(monkeypatch):
    monkeypatch.delenv("INVESTSCOPE_TRUSTED_HOSTS", raising=False)
    assert Settings(_env_file=None).trusted_hosts == ["localhost", "127.0.0.1", "::1"]
    monkeypatch.setenv("INVESTSCOPE_TRUSTED_HOSTS", json.dumps(["API.Example.COM", "192.0.2.1", "2001:db8::1"]))
    assert Settings(_env_file=None).trusted_hosts == ["api.example.com", "192.0.2.1", "2001:db8::1"]


def test_invalid_environment_setting_fails_instead_of_silent_ignore(monkeypatch):
    monkeypatch.setenv("INVESTSCOPE_TRUSTED_HOSTS", '["localhost", "*"]')
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
