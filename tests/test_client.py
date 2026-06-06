import pytest
from neevai.client import NeevAI, AsyncNeevAI
from neevai.errors import NeevAIError

def test_client_initialization_requires_api_key(monkeypatch):
    monkeypatch.delenv("NEEVCLOUD_API_KEY", raising=False)
    with pytest.raises(NeevAIError):
        NeevAI()

@pytest.mark.asyncio
async def test_async_client_initialization_requires_api_key(monkeypatch):
    monkeypatch.delenv("NEEVCLOUD_API_KEY", raising=False)
    with pytest.raises(NeevAIError):
        AsyncNeevAI()
