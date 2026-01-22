"""In-memory registry backend for development and testing."""

import asyncio
from datetime import UTC, datetime, timedelta

from tapper.models import ServiceInfo, ServiceInstance
from tapper.registry.backends.base import RegistryBackend


class InMemoryBackend(RegistryBackend):
    """In-memory implementation of the registry backend.

    Suitable for development and single-instance deployments.
    Data is lost when the process stops.
    """

    def __init__(self) -> None:
        self._services: dict[str, ServiceInfo] = {}
        self._lock = asyncio.Lock()

    async def register(self, service: ServiceInfo, instance: ServiceInstance) -> None:
        """Register a service instance."""
        async with self._lock:
            if service.name in self._services:
                existing = self._services[service.name]
                instance_urls = {inst.url for inst in existing.instances}
                if instance.url in instance_urls:
                    existing.instances = [
                        instance if inst.url == instance.url else inst
                        for inst in existing.instances
                    ]
                else:
                    existing.instances.append(instance)
                existing.routes = service.routes
                existing.version = service.version
                existing.description = service.description
                existing.prefix = service.prefix
                existing.tags = service.tags
            else:
                service_copy = service.model_copy(deep=True)
                service_copy.instances = [instance]
                self._services[service.name] = service_copy

    async def unregister(self, name: str, instance_url: str) -> None:
        """Remove a service instance from the registry."""
        async with self._lock:
            if name in self._services:
                service = self._services[name]
                service.instances = [
                    inst for inst in service.instances if inst.url != instance_url
                ]
                if not service.instances:
                    del self._services[name]

    async def get_service(self, name: str) -> ServiceInfo | None:
        """Get a service by name."""
        async with self._lock:
            service = self._services.get(name)
            if service:
                return service.model_copy(deep=True)
            return None

    async def get_all_services(self) -> list[ServiceInfo]:
        """Get all registered services."""
        async with self._lock:
            return [svc.model_copy(deep=True) for svc in self._services.values()]

    async def heartbeat(self, name: str, instance_url: str) -> None:
        """Update the heartbeat timestamp for a service instance."""
        async with self._lock:
            if name in self._services:
                for instance in self._services[name].instances:
                    if instance.url == instance_url:
                        instance.last_heartbeat = datetime.now(UTC)
                        instance.healthy = True
                        break

    async def cleanup_stale(self, max_age_seconds: int = 60) -> None:
        """Remove instances that haven't sent a heartbeat within max_age_seconds."""
        async with self._lock:
            cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
            services_to_remove = []

            for name, service in self._services.items():
                service.instances = [
                    inst for inst in service.instances
                    if inst.last_heartbeat > cutoff
                ]
                if not service.instances:
                    services_to_remove.append(name)

            for name in services_to_remove:
                del self._services[name]
