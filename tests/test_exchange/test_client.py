import pytest
from app.exchange.client import DeltaClient

def test_delta_client_init():
    client = DeltaClient(base_url="https://cdn-ind.testnet.deltaex.org", api_key="key", api_secret="secret")
    assert client.base_url == "https://cdn-ind.testnet.deltaex.org"
    assert client.api_key == "key"
