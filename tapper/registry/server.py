"""FastAPI-based service registry server."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, status

from tapper.models import (
    HeartbeatRequest,
    RegisterRequest,
    ServiceInfo,
    UnregisterRequest,
)
from tapper.registry.backends.base import RegistryBackend
from tapper.registry.backends.memory import InMemoryBackend


def create_registry_app(
    backend: RegistryBackend | None = None,
    cleanup_interval: int = 30,
    stale_threshold: int = 60,
) -> FastAPI:
    """Create a FastAPI application for the service registry.

    Args:
        backend: Registry backend to use. Defaults to InMemoryBackend.
        cleanup_interval: Seconds between stale instance cleanup runs.
        stale_threshold: Seconds after which an instance is considered stale.
    """
    if backend is None:
        backend = InMemoryBackend()

    cleanup_task: asyncio.Task | None = None

    async def cleanup_loop() -> None:
        """Periodically clean up stale service instances."""
        while True:
            await asyncio.sleep(cleanup_interval)
            await backend.cleanup_stale(stale_threshold)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal cleanup_task
        cleanup_task = asyncio.create_task(cleanup_loop())
        yield
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(
        title="Tapper Service Registry",
        description="Central registry for service discovery",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.post("/register", status_code=status.HTTP_201_CREATED)
    async def register(request: RegisterRequest) -> dict:
        """Register a service instance with the registry."""
        await backend.register(request.service, request.instance)
        return {"status": "registered", "service": request.service.name}

    @app.post("/unregister", status_code=status.HTTP_200_OK)
    async def unregister(request: UnregisterRequest) -> dict:
        """Remove a service instance from the registry."""
        await backend.unregister(request.name, request.instance_url)
        return {"status": "unregistered", "service": request.name}

    @app.get("/services", response_model=list[ServiceInfo])
    async def list_services() -> list[ServiceInfo]:
        """List all registered services."""
        return await backend.get_all_services()

    @app.get("/services/{name}", response_model=ServiceInfo)
    async def get_service(name: str) -> ServiceInfo:
        """Get a specific service by name."""
        service = await backend.get_service(name)
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service not found: {name}",
            )
        return service

    @app.post("/heartbeat/{name}", status_code=status.HTTP_200_OK)
    async def heartbeat(name: str, request: HeartbeatRequest) -> dict:
        """Update heartbeat for a service instance."""
        service = await backend.get_service(name)
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service not found: {name}",
            )
        await backend.heartbeat(name, request.instance_url)
        return {"status": "ok"}

    @app.get("/health")
    async def health() -> dict:
        """Health check endpoint for the registry itself."""
        return {"status": "healthy"}

    return app
