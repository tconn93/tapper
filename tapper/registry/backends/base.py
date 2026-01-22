"""Abstract base class for registry backends."""

from abc import ABC, abstractmethod

from tapper.models import ServiceInfo, ServiceInstance


class RegistryBackend(ABC):
    """Abstract base class for service registry backends."""

    @abstractmethod
    async def register(self, service: ServiceInfo, instance: ServiceInstance) -> None:
        """Register a service instance.

        If the service already exists, adds the instance to it.
        If the instance already exists, updates its information.
        """
        pass

    @abstractmethod
    async def unregister(self, name: str, instance_url: str) -> None:
        """Remove a service instance from the registry."""
        pass

    @abstractmethod
    async def get_service(self, name: str) -> ServiceInfo | None:
        """Get a service by name, or None if not found."""
        pass

    @abstractmethod
    async def get_all_services(self) -> list[ServiceInfo]:
        """Get all registered services."""
        pass

    @abstractmethod
    async def heartbeat(self, name: str, instance_url: str) -> None:
        """Update the heartbeat timestamp for a service instance."""
        pass

    @abstractmethod
    async def cleanup_stale(self, max_age_seconds: int = 60) -> None:
        """Remove instances that haven't sent a heartbeat within max_age_seconds."""
        pass
