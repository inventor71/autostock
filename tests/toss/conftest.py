import copy
import json
from pathlib import Path

import httpx
import pytest

from src.execution.brokers.toss.client import TossClient
from src.execution.brokers.toss.credentials import TossCredentials


@pytest.fixture
def examples():
    return json.loads((Path(__file__).parent / "fixtures/openapi_examples.json").read_text())


@pytest.fixture
def credentials():
    return TossCredentials("test-client", "test-secret", "1")


@pytest.fixture
def client_factory(tmp_path, credentials):
    clients = []

    def make(handler, *, read_only=True, creds=None, state=None):
        calls = []

        def route(request):
            calls.append(request)
            if request.url.path == "/oauth2/token":
                return httpx.Response(200, json={"access_token": "test-access", "expires_in": 86400})
            result = handler(request)
            return result if isinstance(result, httpx.Response) else httpx.Response(200, json={"result": result})

        client = TossClient(
            creds or credentials, read_only=read_only, state_dir=state or tmp_path / "state",
            http=httpx.Client(transport=httpx.MockTransport(route)),
        )
        clients.append(client)
        return client, calls

    yield make
    for client in clients:
        client.close()


@pytest.fixture
def us_order(examples):
    return copy.deepcopy(examples["orders"]["result"]["orders"][1])
