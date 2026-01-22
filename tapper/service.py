"""Service decorator for automatic service registration."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import AsyncIterator, Callable

from fastapi import FastAPI
from fastapi.routing import APIRoute

from tapper.models import Route, ServiceInfo, ServiceInstance
from tapper.registry.client import RegistryClient

logger = logging.getLogger(__name__)


def _extract_routes(app: FastAPI, prefix: str | None = None) -> list[Route]:
    """Extract API routes from a FastAPI application."""
    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            path = route.path
            if prefix and not path.startswith(prefix):
                path = f"{prefix.rstrip('/')}/{path.lstrip('/')}"
            routes.append(Route(path=path, methods=list(route.methods)))
    return routes


class Service:
    """Decorator to register a FastAPI application as a service.

    Usage:
        @Service(name="user-service", version="1.0.0")
        app = FastAPI()

    Or as a function call:
        app = FastAPI()
        app = Service(name="user-service", version="1.0.0")(app)

    The decorator wraps the app's lifespan to:
    - Register the service with the registry on startup
    - Start a background heartbeat task
    - Unregister the service on shutdown
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        description: str | None = None,
        prefix: str | None = None,
        health_endpoint: str = "/health",
        tags: list[str] | None = None,
        registry_url: str | None = None,
        url: str | None = None,
        heartbeat_interval: float = 30.0,
    ) -> None:
        """Initialize the Service decorator.

        Args:
            name: Unique name for the service.
            version: Service version.
            description: Human-readable description.
            prefix: URL prefix for routing.
            health_endpoint: Path to health check endpoint.
            tags: List of tags for categorization.
            registry_url: URL of the registry server.
                         Defaults to TAPPER_REGISTRY_URL env var.
            url: Explicit URL for this instance.
                 If not provided, attempts to auto-detect from uvicorn.
            heartbeat_interval: Seconds between heartbeats.
        """
        self.name = name
        self.version = version
        self.description = description
        self.prefix = prefix
        self.health_endpoint = health_endpoint
        self.tags = tags or []
        self.registry_url = registry_url or os.environ.get(
            "TAPPER_REGISTRY_URL", "http://localhost:8001"
        )
        self.url = url
        self.heartbeat_interval = heartbeat_interval

    def __call__(self, app: FastAPI) -> FastAPI:
        """Apply the decorator to a FastAPI application."""
        original_lifespan = app.router.lifespan_context
        service_decorator = self

        @asynccontextmanager
        async def wrapped_lifespan(app: FastAPI) -> AsyncIterator[None]:
            client = RegistryClient(service_decorator.registry_url)
            instance_url = service_decorator._get_instance_url()

            service_info = ServiceInfo(
                name=service_decorator.name,
                version=service_decorator.version,
                description=service_decorator.description,
                prefix=service_decorator.prefix,
                routes=_extract_routes(app, service_decorator.prefix),
                tags=service_decorator.tags,
            )

            instance = ServiceInstance(
                url=instance_url,
                health_endpoint=service_decorator.health_endpoint,
                last_heartbeat=datetime.now(UTC),
            )

            try:
                await client.register(service_info, instance)
                logger.info(f"Registered service '{service_decorator.name}' at {instance_url}")
                client.start_heartbeat(
                    service_decorator.name,
                    instance_url,
                    service_decorator.heartbeat_interval,
                )
            except Exception as e:
                logger.error(f"Failed to register service: {e}")

            try:
                if original_lifespan is not None:
                    async with original_lifespan(app):
                        yield
                else:
                    yield
            finally:
                try:
                    await client.stop_heartbeat()
                    await client.unregister(service_decorator.name, instance_url)
                    logger.info(f"Unregistered service '{service_decorator.name}'")
                except Exception as e:
                    logger.error(f"Failed to unregister service: {e}")
                finally:
                    await client.close()

        app.router.lifespan_context = wrapped_lifespan
        return app

    def _get_instance_url(self) -> str:
        """Get the URL for this service instance.

        Returns the explicitly configured URL, or attempts to detect
        from environment variables commonly set by uvicorn.
        """
        if self.url:
            return self.url

        host = os.environ.get("UVICORN_HOST", os.environ.get("HOST", "127.0.0.1"))
        port = os.environ.get("UVICORN_PORT", os.environ.get("PORT", "8000"))

        if host == "0.0.0.0":
            host = "127.0.0.1"

        return f"http://{host}:{port}"
