"""Tests for the TapperGateway and load balancers."""

from datetime import UTC, datetime

import pytest

from tapper.exceptions import NoHealthyInstanceError
from tapper.gateway import RouteEntry, TapperGateway
from tapper.load_balancer import (
    LeastConnectionsBalancer,
    RandomBalancer,
    RoundRobinBalancer,
    get_load_balancer,
)
from tapper.models import Route, ServiceInfo, ServiceInstance


class TestLoadBalancers:
    """Tests for load balancer implementations."""

    @pytest.fixture
    def healthy_instances(self) -> list[ServiceInstance]:
        return [
            ServiceInstance(
                url=f"http://localhost:800{i}",
                last_heartbeat=datetime.now(UTC),
                healthy=True,
            )
            for i in range(3)
        ]

    @pytest.fixture
    def mixed_instances(self) -> list[ServiceInstance]:
        return [
            ServiceInstance(
                url="http://localhost:8001",
                last_heartbeat=datetime.now(UTC),
                healthy=True,
            ),
            ServiceInstance(
                url="http://localhost:8002",
                last_heartbeat=datetime.now(UTC),
                healthy=False,
            ),
            ServiceInstance(
                url="http://localhost:8003",
                last_heartbeat=datetime.now(UTC),
                healthy=True,
            ),
        ]

    def test_round_robin_cycles_through_instances(self, healthy_instances):
        balancer = RoundRobinBalancer()

        selected = [
            balancer.select_instance(healthy_instances, "test").url
            for _ in range(6)
        ]

        assert selected[:3] == [
            "http://localhost:8000",
            "http://localhost:8001",
            "http://localhost:8002",
        ]
        assert selected[3:6] == [
            "http://localhost:8000",
            "http://localhost:8001",
            "http://localhost:8002",
        ]

    def test_round_robin_skips_unhealthy(self, mixed_instances):
        balancer = RoundRobinBalancer()

        selected = [
            balancer.select_instance(mixed_instances, "test").url
            for _ in range(4)
        ]

        assert "http://localhost:8002" not in selected

    def test_random_selects_from_healthy(self, healthy_instances):
        balancer = RandomBalancer()

        for _ in range(10):
            selected = balancer.select_instance(healthy_instances, "test")
            assert selected in healthy_instances

    def test_random_skips_unhealthy(self, mixed_instances):
        balancer = RandomBalancer()

        for _ in range(10):
            selected = balancer.select_instance(mixed_instances, "test")
            assert selected.healthy is True

    def test_no_healthy_instances_raises_error(self):
        balancer = RoundRobinBalancer()
        unhealthy = [
            ServiceInstance(
                url="http://localhost:8001",
                last_heartbeat=datetime.now(UTC),
                healthy=False,
            )
        ]

        with pytest.raises(NoHealthyInstanceError):
            balancer.select_instance(unhealthy, "test-service")

    def test_least_connections_selects_minimum(self):
        instances = [
            ServiceInstance(
                url=f"http://localhost:800{i}",
                last_heartbeat=datetime.now(UTC),
                healthy=True,
            )
            for i in range(3)
        ]

        balancer = LeastConnectionsBalancer()
        balancer._connections["http://localhost:8000"] = 5
        balancer._connections["http://localhost:8001"] = 2
        balancer._connections["http://localhost:8002"] = 8

        selected = balancer.select_instance(instances, "test")
        assert selected.url == "http://localhost:8001"

    def test_least_connections_increment_decrement(self):
        balancer = LeastConnectionsBalancer()

        balancer.increment("http://localhost:8001")
        balancer.increment("http://localhost:8001")
        assert balancer._connections["http://localhost:8001"] == 2

        balancer.decrement("http://localhost:8001")
        assert balancer._connections["http://localhost:8001"] == 1

    def test_get_load_balancer_by_name(self):
        assert isinstance(get_load_balancer("round-robin"), RoundRobinBalancer)
        assert isinstance(get_load_balancer("random"), RandomBalancer)
        assert isinstance(get_load_balancer("least-connections"), LeastConnectionsBalancer)

    def test_get_load_balancer_passthrough(self):
        existing = RoundRobinBalancer()
        assert get_load_balancer(existing) is existing

    def test_get_load_balancer_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown load balancer"):
            get_load_balancer("unknown-strategy")


class TestRouteEntry:
    """Tests for route matching."""

    def test_exact_path_match(self):
        service = ServiceInfo(name="test", version="1.0.0", routes=[])
        entry = RouteEntry("/users", {"GET", "POST"}, service)

        assert entry.match("/users", "GET") is not None
        assert entry.match("/users", "POST") is not None
        assert entry.match("/users", "DELETE") is None
        assert entry.match("/other", "GET") is None

    def test_path_parameter_match(self):
        service = ServiceInfo(name="test", version="1.0.0", routes=[])
        entry = RouteEntry("/users/{user_id}", {"GET"}, service)

        params = entry.match("/users/123", "GET")
        assert params is not None
        assert params["user_id"] == "123"

    def test_multiple_path_parameters(self):
        service = ServiceInfo(name="test", version="1.0.0", routes=[])
        entry = RouteEntry("/users/{user_id}/posts/{post_id}", {"GET"}, service)

        params = entry.match("/users/42/posts/99", "GET")
        assert params is not None
        assert params["user_id"] == "42"
        assert params["post_id"] == "99"


class TestTapperGateway:
    """Tests for the TapperGateway."""

    def test_gateway_initialization(self):
        gateway = TapperGateway(
            registry_url="http://localhost:8001",
            discovery_interval=60,
            timeout=15.0,
            load_balancer="random",
        )

        assert gateway.registry_url == "http://localhost:8001"
        assert gateway.discovery_interval == 60
        assert gateway.timeout == 15.0
        assert isinstance(gateway.load_balancer, RandomBalancer)

    def test_gateway_default_registry_url(self, monkeypatch):
        monkeypatch.delenv("TAPPER_REGISTRY_URL", raising=False)

        gateway = TapperGateway()
        assert gateway.registry_url == "http://localhost:8001"

    def test_gateway_registry_url_from_env(self, monkeypatch):
        monkeypatch.setenv("TAPPER_REGISTRY_URL", "http://registry:9000")

        gateway = TapperGateway()
        assert gateway.registry_url == "http://registry:9000"

    def test_build_route_table(self):
        gateway = TapperGateway()

        gateway._services = [
            ServiceInfo(
                name="user-service",
                version="1.0.0",
                routes=[
                    Route(path="/users", methods=["GET", "POST"]),
                    Route(path="/users/{user_id}", methods=["GET"]),
                ],
            ),
            ServiceInfo(
                name="order-service",
                version="1.0.0",
                routes=[
                    Route(path="/orders", methods=["GET"]),
                ],
            ),
        ]

        gateway._build_route_table()

        assert len(gateway._routes) == 3

    def test_match_route(self):
        gateway = TapperGateway()

        service = ServiceInfo(
            name="user-service",
            version="1.0.0",
            routes=[Route(path="/users/{user_id}", methods=["GET"])],
        )
        gateway._services = [service]
        gateway._build_route_table()

        match = gateway._match_route("/users/123", "GET")
        assert match is not None
        matched_service, params = match
        assert matched_service.name == "user-service"
        assert params["user_id"] == "123"

    def test_match_route_not_found(self):
        gateway = TapperGateway()
        gateway._services = []
        gateway._build_route_table()

        match = gateway._match_route("/nonexistent", "GET")
        assert match is None
