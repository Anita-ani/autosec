"""
Shared pytest fixtures for AutoSecOps tests.
Uses httpx.AsyncClient with the FastAPI app — no real MongoDB or n8n required.
MongoDB and n8n calls are patched out so tests run with zero infrastructure.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
import os

# Set required env vars before importing the app
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("API_KEY", "test-api-key-1234")
os.environ.setdefault("N8N_WEBHOOK_BASE", "http://localhost:5678/webhook")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-phase6")

from backend.main import app
from backend.services.auth import create_access_token

VALID_KEY = "test-api-key-1234"
HEADERS = {"X-API-Key": VALID_KEY}


def make_jwt(role: str = "operator", username: str = "testuser") -> str:
    return create_access_token({"sub": username, "role": role})


def jwt_headers(role: str = "operator") -> dict:
    return {"Authorization": f"Bearer {make_jwt(role)}"}


@pytest_asyncio.fixture
async def client(mock_mongo, mock_n8n):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=HEADERS,
    ) as ac:
        yield ac


@pytest.fixture(autouse=True)
def mock_mongo():
    """Patch MongoDB so no real connection is needed."""
    fake_aggregate_cursor = MagicMock()
    fake_aggregate_cursor.to_list = AsyncMock(return_value=[])

    fake_collection = MagicMock()
    fake_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="64f1a2b3c4d5e6f7a8b9c0d1"))
    fake_collection.find = MagicMock(return_value=_async_cursor([]))
    fake_collection.find_one = AsyncMock(return_value=None)
    fake_collection.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    fake_collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    fake_collection.count_documents = AsyncMock(return_value=0)
    fake_collection.aggregate = MagicMock(return_value=fake_aggregate_cursor)
    fake_collection.create_index = AsyncMock()

    fake_db = MagicMock()
    fake_db.__getitem__ = MagicMock(return_value=fake_collection)
    fake_db.events = fake_collection
    fake_db.alerts = fake_collection
    fake_db.blocked_ips = fake_collection
    fake_db.audit_logs = fake_collection
    fake_db.webhooks = fake_collection
    fake_db.webhook_delivery_log = fake_collection

    # Patch admin ping for health check
    fake_admin = MagicMock()
    fake_admin.command = AsyncMock(return_value={"ok": 1})
    fake_client = MagicMock()
    fake_client.admin = fake_admin
    fake_client.__getitem__ = MagicMock(return_value=fake_db)

    with patch("backend.services.mongo.get_client", return_value=fake_client), \
         patch("backend.services.mongo.get_db", return_value=fake_db), \
         patch("backend.services.mongo.init_indexes", new_callable=AsyncMock), \
         patch("backend.services.mongo.close_client", new_callable=AsyncMock):
        yield fake_db


@pytest.fixture(autouse=True)
def mock_n8n():
    """Patch n8n so no real HTTP calls are made."""
    with patch("backend.services.n8n.forward_event", new_callable=AsyncMock) as fwd_event, \
         patch("backend.services.n8n.forward_block", new_callable=AsyncMock) as fwd_block:
        yield fwd_event, fwd_block


@pytest.fixture(autouse=True)
def mock_geo():
    """Patch geo lookup so no real HTTP calls are made in tests."""
    with patch("backend.routes.events.geo.lookup", new_callable=AsyncMock, return_value={}) as mock_lookup:
        yield mock_lookup


class _async_cursor:
    """Minimal async cursor stub for motor find() calls."""
    def __init__(self, items):
        self._items = iter(items)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, n):
        return self

    def limit(self, n):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration
