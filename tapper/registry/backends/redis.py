"""Redis-based registry backend for distributed deployments."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from tapper.models import ServiceInfo, ServiceInstance
from tapper.registry.backends.base import RegistryBackend

try:
    import redis.asyncio as redis
except ImportError:
    redis = None  # type: ignore


class RedisBackend(RegistryBackend):
    """Redis-based implementation of the registry backend.

    Suitable for distributed deployments where multiple registry instances
    need to share state.

    Requires the 'redis' optional dependency: pip install tapper[redis]
    """

    SERVICE_KEY_PREFIX = "tapper:service:"
    INSTANCE_KEY_PREFIX = "tapper:instance:"
    DEFAULT_INSTANCE_TTL = 90  # seconds

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        instance_ttl: int = DEFAULT_INSTANCE_TTL,
    ) -> None:
        if redis is None:
            raise ImportError(
                "Redis support requires the 'redis' package. "
                "Install with: pip install tapper[redis]"
            )
        self._redis_url = redis_url
        self._instance_ttl = instance_ttl
        self._client: redis.Redis | None = None

    async def _get_client(self) -> "redis.Redis":
        """Get or create the Redis client."""
        if self._client is None:
            self._client = redis.from_url(self._redis_url)
        return self._client

    def _service_key(self, name: str) -> str:
        """Generate Redis key for service info."""
        return f"{self.SERVICE_KEY_PREFIX}{name}"

    def _instance_key(self, name: str, url: str) -> str:
        """Generate Redis key for service instance."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        return f"{self.INSTANCE_KEY_PREFIX}{name}:{url_hash}"

    async def register(self, service: ServiceInfo, instance: ServiceInstance) -> None:
        """Register a service instance."""
        client = await self._get_client()

        service_data = service.model_dump(mode="json")
        service_data["instances"] = []
        await client.set(
            self._service_key(service.name),
            json.dumps(service_data),
        )

        instance_data = instance.model_dump(mode="json")
        await client.setex(
            self._instance_key(service.name, instance.url),
            self._instance_ttl,
            json.dumps(instance_data),
        )

    async def unregister(self, name: str, instance_url: str) -> None:
        """Remove a service instance from the registry."""
        client = await self._get_client()
        await client.delete(self._instance_key(name, instance_url))

        instances = await self._get_instances(name)
        if not instances:
            await client.delete(self._service_key(name))

    async def _get_instances(self, name: str) -> list[ServiceInstance]:
        """Get all instances for a service."""
        client = await self._get_client()
        pattern = f"{self.INSTANCE_KEY_PREFIX}{name}:*"
        instances = []

        async for key in client.scan_iter(match=pattern):
            data = await client.get(key)
            if data:
                instance_data = json.loads(data)
                instance_data["last_heartbeat"] = datetime.fromisoformat(
                    instance_data["last_heartbeat"]
                )
                instances.append(ServiceInstance(**instance_data))

        return instances

    async def get_service(self, name: str) -> ServiceInfo | None:
        """Get a service by name."""
        client = await self._get_client()
        data = await client.get(self._service_key(name))

        if not data:
            return None

        service_data = json.loads(data)
        instances = await self._get_instances(name)
        service_data["instances"] = [inst.model_dump() for inst in instances]

        return ServiceInfo(**service_data)

    async def get_all_services(self) -> list[ServiceInfo]:
        """Get all registered services."""
        client = await self._get_client()
        pattern = f"{self.SERVICE_KEY_PREFIX}*"
        services = []

        async for key in client.scan_iter(match=pattern):
            name = key.decode() if isinstance(key, bytes) else key
            name = name.replace(self.SERVICE_KEY_PREFIX, "")
            service = await self.get_service(name)
            if service:
                services.append(service)

        return services

    async def heartbeat(self, name: str, instance_url: str) -> None:
        """Update the heartbeat timestamp for a service instance."""
        client = await self._get_client()
        key = self._instance_key(name, instance_url)
        data = await client.get(key)

        if data:
            instance_data = json.loads(data)
            instance_data["last_heartbeat"] = datetime.now(UTC).isoformat()
            instance_data["healthy"] = True
            await client.setex(key, self._instance_ttl, json.dumps(instance_data))

    async def cleanup_stale(self, max_age_seconds: int = 60) -> None:
        """Remove stale instances.

        Note: With Redis, TTL handles automatic expiration.
        This method is provided for manual cleanup if needed.
        """
        client = await self._get_client()
        cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)

        for service in await self.get_all_services():
            for instance in service.instances:
                if instance.last_heartbeat < cutoff:
                    await client.delete(
                        self._instance_key(service.name, instance.url)
                    )

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
