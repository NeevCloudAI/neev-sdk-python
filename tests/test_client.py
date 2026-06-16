import pytest

from neevai.client import AsyncNeevAI, NeevAI
from neevai.errors import NeevAIError


def test_client_initialization_requires_api_key(monkeypatch):
    monkeypatch.delenv("NEEVCLOUD_API_KEY", raising=False)
    monkeypatch.delenv("NEEV_API_KEY", raising=False)
    with pytest.raises(NeevAIError):
        NeevAI()


@pytest.mark.asyncio
async def test_async_client_initialization_requires_api_key(monkeypatch):
    monkeypatch.delenv("NEEVCLOUD_API_KEY", raising=False)
    monkeypatch.delenv("NEEV_API_KEY", raising=False)
    with pytest.raises(NeevAIError):
        AsyncNeevAI()


def test_client_reads_neev_env_aliases(monkeypatch):
    monkeypatch.delenv("NEEVCLOUD_API_KEY", raising=False)
    monkeypatch.delenv("NEEVCLOUD_ORG_ID", raising=False)
    monkeypatch.delenv("NEEVCLOUD_PROJECT_ID", raising=False)
    monkeypatch.delenv("NEEVCLOUD_BASE_URL", raising=False)
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
    monkeypatch.setenv("NEEVCLOUD_API_KEY", "test")
    monkeypatch.delenv("NEEVCLOUD_BASE_URL", raising=False)
    monkeypatch.delenv("NEEV_BASE_URL", raising=False)
    client = NeevAI()
    assert client.base_url == "https://api.ai.neevcloud.com/agent"
    client.close()


def test_client_reads_region_from_env(monkeypatch):
    monkeypatch.setenv("NEEVCLOUD_API_KEY", "test")
    monkeypatch.setenv("NEEVCLOUD_REGION", "eu-west-1")
    client = NeevAI()
    assert client.default_region == "eu-west-1"
    assert client._resolve_region() == "eu-west-1"
    client.close()


def test_client_region_kwarg_overrides_env(monkeypatch):
    monkeypatch.setenv("NEEVCLOUD_API_KEY", "test")
    monkeypatch.setenv("NEEVCLOUD_REGION", "eu-west-1")
    client = NeevAI(region="us-east-1")
    assert client.default_region == "us-east-1"
    client.close()


def test_resolve_region_raises_when_missing(monkeypatch):
    monkeypatch.setenv("NEEVCLOUD_API_KEY", "test")
    monkeypatch.delenv("NEEVCLOUD_REGION", raising=False)
    client = NeevAI()
    with pytest.raises(NeevAIError, match="Missing region"):
        client._resolve_region()
    client.close()


@pytest.mark.asyncio
async def test_async_client_reads_region_from_env(monkeypatch):
    monkeypatch.setenv("NEEVCLOUD_API_KEY", "test")
    monkeypatch.setenv("NEEVCLOUD_REGION", "eu-west-1")
    client = AsyncNeevAI()
    assert client.default_region == "eu-west-1"
    assert client._resolve_region() == "eu-west-1"
    await client.aclose()


@pytest.mark.asyncio
async def test_async_resolve_region_raises_when_missing(monkeypatch):
    monkeypatch.setenv("NEEVCLOUD_API_KEY", "test")
    monkeypatch.delenv("NEEVCLOUD_REGION", raising=False)
    client = AsyncNeevAI()
    with pytest.raises(NeevAIError, match="Missing region"):
        client._resolve_region()
    await client.aclose()
