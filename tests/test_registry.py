"""Tests for the registry server and backends."""

from datetime import UTC, datetime, timedelta

import pytest

from tapper.models import Route, ServiceInfo, ServiceInstance
from tapper.registry.backends.memory import InMemoryBackend


class TestInMemoryBackend:
    """Tests for the in-memory registry backend."""

    @pytest.fixture
    def backend(self) -> InMemoryBackend:
        return InMemoryBackend()

    @pytest.fixture
    def service(self) -> ServiceInfo:
        return ServiceInfo(
            name="test-service",
            version="1.0.0",
            routes=[Route(path="/test", methods=["GET"])],
        )

    @pytest.fixture
    def instance(self) -> ServiceInstance:
        return ServiceInstance(
            url="http://localhost:8001",
            last_heartbeat=datetime.now(UTC),
        )

    async def test_register_new_service(
        self,
        backend: InMemoryBackend,
        service: ServiceInfo,
        instance: ServiceInstance,
    ):
        await backend.register(service, instance)
        result = await backend.get_service("test-service")

        assert result is not None
        assert result.name == "test-service"
        assert len(result.instances) == 1
        assert result.instances[0].url == "http://localhost:8001"

    async def test_register_additional_instance(
        self,
        backend: InMemoryBackend,
        service: ServiceInfo,
        instance: ServiceInstance,
    ):
        await backend.register(service, instance)

        second_instance = ServiceInstance(
            url="http://localhost:8002",
            last_heartbeat=datetime.now(UTC),
        )
        await backend.register(service, second_instance)

        result = await backend.get_service("test-service")
        assert result is not None
        assert len(result.instances) == 2

    async def test_unregister_instance(
        self,
        backend: InMemoryBackend,
        service: ServiceInfo,
        instance: ServiceInstance,
    ):
        await backend.register(service, instance)
        await backend.unregister("test-service", "http://localhost:8001")

        result = await backend.get_service("test-service")
        assert result is None

    async def test_unregister_one_of_multiple_instances(
        self,
        backend: InMemoryBackend,
        service: ServiceInfo,
        instance: ServiceInstance,
    ):
        await backend.register(service, instance)

        second_instance = ServiceInstance(
            url="http://localhost:8002",
            last_heartbeat=datetime.now(UTC),
        )
        await backend.register(service, second_instance)

        await backend.unregister("test-service", "http://localhost:8001")

        result = await backend.get_service("test-service")
        assert result is not None
        assert len(result.instances) == 1
        assert result.instances[0].url == "http://localhost:8002"

    async def test_get_all_services(
        self,
        backend: InMemoryBackend,
        service: ServiceInfo,
        instance: ServiceInstance,
    ):
        await backend.register(service, instance)

        service2 = ServiceInfo(
            name="another-service",
            version="2.0.0",
            routes=[],
        )
        instance2 = ServiceInstance(
            url="http://localhost:9001",
            last_heartbeat=datetime.now(UTC),
        )
        await backend.register(service2, instance2)

        all_services = await backend.get_all_services()
        assert len(all_services) == 2
        names = {s.name for s in all_services}
        assert names == {"test-service", "another-service"}

    async def test_heartbeat_updates_timestamp(
        self,
        backend: InMemoryBackend,
        service: ServiceInfo,
        instance: ServiceInstance,
    ):
        await backend.register(service, instance)

        old_time = instance.last_heartbeat
        await backend.heartbeat("test-service", "http://localhost:8001")

        result = await backend.get_service("test-service")
        assert result is not None
        assert result.instances[0].last_heartbeat >= old_time

    async def test_cleanup_stale_instances(
        self,
        backend: InMemoryBackend,
        service: ServiceInfo,
    ):
        old_instance = ServiceInstance(
            url="http://localhost:8001",
            last_heartbeat=datetime.now(UTC) - timedelta(seconds=120),
        )
        await backend.register(service, old_instance)

        await backend.cleanup_stale(max_age_seconds=60)

        result = await backend.get_service("test-service")
        assert result is None


class TestRegistryServer:
    """Tests for the registry HTTP server."""

    async def test_register_service(self, registry_client, sample_service_info, sample_instance):
        response = await registry_client.post(
            "/register",
            json={
                "service": sample_service_info.model_dump(mode="json"),
                "instance": sample_instance.model_dump(mode="json"),
            },
        )
        assert response.status_code == 201
        assert response.json()["status"] == "registered"

    async def test_list_services(self, registry_client, sample_service_info, sample_instance):
        await registry_client.post(
            "/register",
            json={
                "service": sample_service_info.model_dump(mode="json"),
                "instance": sample_instance.model_dump(mode="json"),
            },
        )

        response = await registry_client.get("/services")
        assert response.status_code == 200
        services = response.json()
        assert len(services) == 1
        assert services[0]["name"] == "test-service"

    async def test_get_service(self, registry_client, sample_service_info, sample_instance):
        await registry_client.post(
            "/register",
            json={
                "service": sample_service_info.model_dump(mode="json"),
                "instance": sample_instance.model_dump(mode="json"),
            },
        )

        response = await registry_client.get("/services/test-service")
        assert response.status_code == 200
        service = response.json()
        assert service["name"] == "test-service"

    async def test_get_nonexistent_service(self, registry_client):
        response = await registry_client.get("/services/nonexistent")
        assert response.status_code == 404

    async def test_unregister_service(self, registry_client, sample_service_info, sample_instance):
        await registry_client.post(
            "/register",
            json={
                "service": sample_service_info.model_dump(mode="json"),
                "instance": sample_instance.model_dump(mode="json"),
            },
        )

        response = await registry_client.post(
            "/unregister",
            json={
                "name": "test-service",
                "instance_url": "http://localhost:8002",
            },
        )
        assert response.status_code == 200

        response = await registry_client.get("/services/test-service")
        assert response.status_code == 404

    async def test_heartbeat(self, registry_client, sample_service_info, sample_instance):
        await registry_client.post(
            "/register",
            json={
                "service": sample_service_info.model_dump(mode="json"),
                "instance": sample_instance.model_dump(mode="json"),
            },
        )

        response = await registry_client.post(
            "/heartbeat/test-service",
            json={"instance_url": "http://localhost:8002"},
        )
        assert response.status_code == 200

    async def test_health_endpoint(self, registry_client):
        response = await registry_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
