import pytest

from neevai.client import AsyncNeevAI, NeevAI
from neevai.errors import NeevAIError


def test_client_initialization_requires_api_key(monkeypatch):
    monkeypatch.delenv("NEEV_API_KEY", raising=False)
    with pytest.raises(NeevAIError):
        NeevAI()


@pytest.mark.asyncio
async def test_async_client_initialization_requires_api_key(monkeypatch):
    monkeypatch.delenv("NEEV_API_KEY", raising=False)
    with pytest.raises(NeevAIError):
        AsyncNeevAI()


def test_client_reads_neev_env_aliases(monkeypatch):
    monkeypatch.delenv("NEEV_API_KEY", raising=False)
    monkeypatch.delenv("NEEV_ORG_ID", raising=False)
    monkeypatch.delenv("NEEV_PROJECT_ID", raising=False)
    monkeypatch.delenv("NEEV_BASE_URL", raising=False)
    monkeypatch.setenv("NEEV_API_KEY", "neev-key")
    monkeypatch.setenv("NEEV_ORG_ID", "neev-org")
    monkeypatch.setenv("NEEV_PROJECT_ID", "neev-proj")
    monkeypatch.setenv("NEEV_BASE_URL", "https://custom.example.com/agent")
    client = NeevAI()
    assert client.base_url == "https://custom.example.com/agent"
    assert client.default_org_id == "neev-org"
    assert client.default_project_id == "neev-proj"
    client.close()


def test_client_default_base_url(monkeypatch):
    monkeypatch.setenv("NEEV_API_KEY", "test")
    monkeypatch.delenv("NEEV_BASE_URL", raising=False)
    client = NeevAI()
    assert client.base_url == "https://api.ai.neevcloud.com/agent"
    client.close()
