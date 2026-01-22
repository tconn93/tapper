"""Pytest fixtures for Tapper tests."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tapper.models import Route, ServiceInfo, ServiceInstance
from tapper.registry.backends.memory import InMemoryBackend
from tapper.registry.server import create_registry_app


@pytest.fixture
def sample_service_info() -> ServiceInfo:
    """Create a sample ServiceInfo for testing."""
    return ServiceInfo(
        name="test-service",
        version="1.0.0",
        description="A test service",
        prefix="/api",
        routes=[
            Route(path="/users", methods=["GET", "POST"]),
            Route(path="/users/{user_id}", methods=["GET", "PUT", "DELETE"]),
        ],
        tags=["test"],
    )


@pytest.fixture
def sample_instance() -> ServiceInstance:
    """Create a sample ServiceInstance for testing."""
    return ServiceInstance(
        url="http://localhost:8002",
        health_endpoint="/health",
        last_heartbeat=datetime.now(UTC),
        healthy=True,
    )


@pytest.fixture
def memory_backend() -> InMemoryBackend:
    """Create an in-memory backend for testing."""
    return InMemoryBackend()


@pytest.fixture
def registry_app(memory_backend: InMemoryBackend) -> FastAPI:
    """Create a registry app with in-memory backend."""
    return create_registry_app(
        backend=memory_backend,
        cleanup_interval=300,  # Long interval for tests
        stale_threshold=60,
    )


@pytest.fixture
async def registry_client(registry_app: FastAPI):
    """Create an async client for the registry app."""
    transport = ASGITransport(app=registry_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def test_fastapi_app() -> FastAPI:
    """Create a test FastAPI application."""
    app = FastAPI()

    @app.get("/users")
    async def list_users():
        return [{"id": 1, "name": "Test User"}]

    @app.get("/users/{user_id}")
    async def get_user(user_id: int):
        return {"id": user_id, "name": "Test User"}

    @app.post("/users")
    async def create_user(name: str = "New User"):
        return {"id": 2, "name": name}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app
