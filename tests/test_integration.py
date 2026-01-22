"""Integration tests for the full Tapper flow."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tapper.gateway import TapperGateway
from tapper.models import Route, ServiceInfo, ServiceInstance
from tapper.registry.backends.memory import InMemoryBackend
from tapper.registry.server import create_registry_app


class TestFullFlow:
    """Integration tests for registry -> gateway -> service flow."""

    @pytest.fixture
    def backend(self) -> InMemoryBackend:
        return InMemoryBackend()

    @pytest.fixture
    def registry_app(self, backend: InMemoryBackend) -> FastAPI:
        return create_registry_app(backend=backend)

    @pytest.fixture
    def user_service(self) -> FastAPI:
        """Create a mock user service."""
        app = FastAPI()

        @app.get("/users")
        async def list_users():
            return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

        @app.get("/users/{user_id}")
        async def get_user(user_id: int):
            return {"id": user_id, "name": f"User {user_id}"}

        @app.post("/users")
        async def create_user():
            return {"id": 3, "name": "New User"}

        return app

    async def test_service_registration_and_discovery(
        self,
        registry_app: FastAPI,
        backend: InMemoryBackend,
    ):
        """Test that services can register and be discovered."""
        transport = ASGITransport(app=registry_app)
        async with AsyncClient(transport=transport, base_url="http://registry") as client:
            service = ServiceInfo(
                name="user-service",
                version="1.0.0",
                routes=[
                    Route(path="/users", methods=["GET", "POST"]),
                    Route(path="/users/{user_id}", methods=["GET"]),
                ],
            )
            instance = ServiceInstance(
                url="http://user-service:8000",
                last_heartbeat=datetime.now(UTC),
            )

            response = await client.post(
                "/register",
                json={
                    "service": service.model_dump(mode="json"),
                    "instance": instance.model_dump(mode="json"),
                },
            )
            assert response.status_code == 201

            response = await client.get("/services")
            services = response.json()
            assert len(services) == 1
            assert services[0]["name"] == "user-service"

    async def test_gateway_routes_to_service(
        self,
        registry_app: FastAPI,
        backend: InMemoryBackend,
        user_service: FastAPI,
    ):
        """Test that gateway correctly routes requests to services."""
        service = ServiceInfo(
            name="user-service",
            version="1.0.0",
            routes=[
                Route(path="/users", methods=["GET", "POST"]),
                Route(path="/users/{user_id}", methods=["GET"]),
            ],
        )
        instance = ServiceInstance(
            url="http://user-service:8000",
            last_heartbeat=datetime.now(UTC),
        )
        await backend.register(service, instance)

        gateway = TapperGateway()

        gateway._services = [
            ServiceInfo(
                name="user-service",
                version="1.0.0",
                routes=[
                    Route(path="/users", methods=["GET", "POST"]),
                    Route(path="/users/{user_id}", methods=["GET"]),
                ],
                instances=[instance],
            )
        ]
        gateway._build_route_table()

        match = gateway._match_route("/users", "GET")
        assert match is not None
        matched_service, _ = match
        assert matched_service.name == "user-service"

        match = gateway._match_route("/users/42", "GET")
        assert match is not None
        matched_service, params = match
        assert matched_service.name == "user-service"
        assert params["user_id"] == "42"

    async def test_multiple_services(
        self,
        backend: InMemoryBackend,
    ):
        """Test routing with multiple services."""
        user_service = ServiceInfo(
            name="user-service",
            version="1.0.0",
            routes=[Route(path="/users", methods=["GET"])],
        )
        user_instance = ServiceInstance(
            url="http://user-service:8000",
            last_heartbeat=datetime.now(UTC),
        )
        await backend.register(user_service, user_instance)

        order_service = ServiceInfo(
            name="order-service",
            version="1.0.0",
            routes=[Route(path="/orders", methods=["GET"])],
        )
        order_instance = ServiceInstance(
            url="http://order-service:8000",
            last_heartbeat=datetime.now(UTC),
        )
        await backend.register(order_service, order_instance)

        services = await backend.get_all_services()
        assert len(services) == 2

        gateway = TapperGateway()
        gateway._services = services
        gateway._build_route_table()

        user_match = gateway._match_route("/users", "GET")
        assert user_match is not None
        assert user_match[0].name == "user-service"

        order_match = gateway._match_route("/orders", "GET")
        assert order_match is not None
        assert order_match[0].name == "order-service"

    async def test_gateway_health_check(self):
        """Test gateway's built-in health check."""
        gateway = TapperGateway()
        gateway._started = True  # Skip startup for this test

        transport = ASGITransport(app=gateway)
        async with AsyncClient(transport=transport, base_url="http://gateway") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

    async def test_gateway_returns_404_for_unknown_route(self):
        """Test that gateway returns 404 for unmatched routes."""
        gateway = TapperGateway()
        gateway._started = True
        gateway._services = []
        gateway._build_route_table()

        transport = ASGITransport(app=gateway)
        async with AsyncClient(transport=transport, base_url="http://gateway") as client:
            response = await client.get("/unknown/route")
            assert response.status_code == 404
            assert response.json()["error"] == "Not found"

    async def test_load_balancing_across_instances(
        self,
        backend: InMemoryBackend,
    ):
        """Test that load balancer distributes across instances."""
        from tapper.load_balancer import RoundRobinBalancer

        service = ServiceInfo(
            name="user-service",
            version="1.0.0",
            routes=[Route(path="/users", methods=["GET"])],
        )

        for i in range(3):
            instance = ServiceInstance(
                url=f"http://user-service-{i}:8000",
                last_heartbeat=datetime.now(UTC),
            )
            await backend.register(service, instance)

        result = await backend.get_service("user-service")
        assert result is not None
        assert len(result.instances) == 3

        balancer = RoundRobinBalancer()
        selected_urls = [
            balancer.select_instance(result.instances, "user-service").url
            for _ in range(6)
        ]

        assert len(set(selected_urls[:3])) == 3
