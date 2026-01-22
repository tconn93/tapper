"""Async client for communicating with the service registry."""

import asyncio
import logging

import httpx

from tapper.exceptions import RegistryError
from tapper.models import ServiceInfo, ServiceInstance

logger = logging.getLogger(__name__)


class RegistryClient:
    """Async client for the Tapper service registry.

    Handles registration, unregistration, heartbeats, and service discovery.
    """

    def __init__(
        self,
        registry_url: str,
        timeout: float = 10.0,
    ) -> None:
        """Initialize the registry client.

        Args:
            registry_url: Base URL of the registry server.
            timeout: Request timeout in seconds.
        """
        self._registry_url = registry_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._heartbeat_task: asyncio.Task | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def register(
        self,
        service: ServiceInfo,
        instance: ServiceInstance,
    ) -> None:
        """Register a service instance with the registry.

        Args:
            service: Service information including routes.
            instance: Instance-specific information.

        Raises:
            RegistryError: If registration fails.
        """
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self._registry_url}/register",
                json={
                    "service": service.model_dump(mode="json"),
                    "instance": instance.model_dump(mode="json"),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise RegistryError(f"Failed to register service: {e}") from e

    async def unregister(self, name: str, instance_url: str) -> None:
        """Remove a service instance from the registry.

        Args:
            name: Service name.
            instance_url: URL of the instance to unregister.

        Raises:
            RegistryError: If unregistration fails.
        """
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self._registry_url}/unregister",
                json={"name": name, "instance_url": instance_url},
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise RegistryError(f"Failed to unregister service: {e}") from e

    async def get_services(self) -> list[ServiceInfo]:
        """Get all registered services from the registry.

        Returns:
            List of registered services.

        Raises:
            RegistryError: If the request fails.
        """
        client = await self._get_client()
        try:
            response = await client.get(f"{self._registry_url}/services")
            response.raise_for_status()
            return [ServiceInfo(**svc) for svc in response.json()]
        except httpx.HTTPError as e:
            raise RegistryError(f"Failed to get services: {e}") from e

    async def get_service(self, name: str) -> ServiceInfo | None:
        """Get a specific service by name.

        Args:
            name: Service name.

        Returns:
            Service information or None if not found.

        Raises:
            RegistryError: If the request fails (except 404).
        """
        client = await self._get_client()
        try:
            response = await client.get(f"{self._registry_url}/services/{name}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return ServiceInfo(**response.json())
        except httpx.HTTPError as e:
            raise RegistryError(f"Failed to get service: {e}") from e

    async def heartbeat(self, name: str, instance_url: str) -> None:
        """Send a heartbeat for a service instance.

        Args:
            name: Service name.
            instance_url: URL of the instance.

        Raises:
            RegistryError: If the heartbeat fails.
        """
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self._registry_url}/heartbeat/{name}",
                json={"instance_url": instance_url},
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"Heartbeat failed for {name}: {e}")
            raise RegistryError(f"Heartbeat failed: {e}") from e

    def start_heartbeat(
        self,
        name: str,
        instance_url: str,
        interval: float = 30.0,
    ) -> None:
        """Start a background task to send periodic heartbeats.

        Args:
            name: Service name.
            instance_url: URL of the instance.
            interval: Seconds between heartbeats.
        """
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()

        async def heartbeat_loop() -> None:
            while True:
                try:
                    await self.heartbeat(name, instance_url)
                except RegistryError:
                    pass  # Already logged in heartbeat()
                await asyncio.sleep(interval)

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        """Stop the background heartbeat task."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def close(self) -> None:
        """Close the client and stop any background tasks."""
        await self.stop_heartbeat()
        if self._client is not None:
            await self._client.aclose()
            self._client = None
