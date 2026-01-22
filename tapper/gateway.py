"""API Gateway for routing requests to registered services."""

import asyncio
import logging
import os
import re
from typing import Any, Callable

import httpx
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import compile_path

from tapper.exceptions import NoHealthyInstanceError, ServiceNotFoundError
from tapper.load_balancer import LoadBalancer, get_load_balancer
from tapper.models import ServiceInfo
from tapper.registry.client import RegistryClient

logger = logging.getLogger(__name__)

Scope = dict[str, Any]
Receive = Callable[[], Any]
Send = Callable[[dict[str, Any]], Any]


class RouteEntry:
    """A compiled route entry for matching incoming requests."""

    def __init__(self, path_pattern: str, methods: set[str], service: ServiceInfo):
        self.path_pattern = path_pattern
        self.methods = methods
        self.service = service
        self._regex, _, self._convertors = compile_path(path_pattern)

    def match(self, path: str, method: str) -> dict[str, Any] | None:
        """Check if the given path and method match this route.

        Returns path parameters if matched, None otherwise.
        """
        if method not in self.methods:
            return None

        match = self._regex.match(path)
        if match:
            params = {}
            for key, value in match.groupdict().items():
                if key in self._convertors:
                    params[key] = self._convertors[key].convert(value)
                else:
                    params[key] = value
            return params
        return None


class TapperGateway:
    """ASGI application that acts as an API gateway.

    Routes incoming requests to registered services based on their
    declared routes, with load balancing across available instances.
    """

    def __init__(
        self,
        registry_url: str | None = None,
        discovery_interval: int = 30,
        timeout: float = 30.0,
        load_balancer: LoadBalancer | str = "round-robin",
    ) -> None:
        """Initialize the gateway.

        Args:
            registry_url: URL of the registry server.
                         Defaults to TAPPER_REGISTRY_URL env var.
            discovery_interval: Seconds between service discovery refreshes.
            timeout: Request timeout in seconds.
            load_balancer: Load balancer instance or strategy name.
        """
        self.registry_url = registry_url or os.environ.get(
            "TAPPER_REGISTRY_URL", "http://localhost:8001"
        )
        self.discovery_interval = discovery_interval
        self.timeout = timeout
        self.load_balancer = get_load_balancer(load_balancer)

        self._client: RegistryClient | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._services: list[ServiceInfo] = []
        self._routes: list[RouteEntry] = []
        self._discovery_task: asyncio.Task | None = None
        self._started = False

    async def _get_client(self) -> RegistryClient:
        """Get or create the registry client."""
        if self._client is None:
            self._client = RegistryClient(self.registry_url)
        return self._client

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client for proxying."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client

    async def _refresh_services(self) -> None:
        """Refresh the service list from the registry."""
        try:
            client = await self._get_client()
            self._services = await client.get_services()
            self._build_route_table()
            logger.debug(f"Refreshed services: {[s.name for s in self._services]}")
        except Exception as e:
            logger.error(f"Failed to refresh services: {e}")

    def _build_route_table(self) -> None:
        """Build the route table from registered services."""
        routes = []
        for service in self._services:
            for route in service.routes:
                routes.append(RouteEntry(
                    path_pattern=route.path,
                    methods=set(route.methods),
                    service=service,
                ))
        self._routes = routes

    def _match_route(self, path: str, method: str) -> tuple[ServiceInfo, dict[str, Any]] | None:
        """Find a matching route for the given path and method."""
        for entry in self._routes:
            params = entry.match(path, method)
            if params is not None:
                return entry.service, params
        return None

    async def _discovery_loop(self) -> None:
        """Periodically refresh the service list."""
        while True:
            await self._refresh_services()
            await asyncio.sleep(self.discovery_interval)

    async def _startup(self) -> None:
        """Start background tasks."""
        if self._started:
            return

        await self._refresh_services()
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        self._started = True

    async def _shutdown(self) -> None:
        """Clean up resources."""
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass

        if self._client:
            await self._client.close()

        if self._http_client:
            await self._http_client.aclose()

    async def _proxy_request(
        self,
        request: Request,
        service: ServiceInfo,
    ) -> Response:
        """Proxy a request to a service instance."""
        if not service.instances:
            raise NoHealthyInstanceError(service.name)

        instance = self.load_balancer.select_instance(
            service.instances,
            service.name,
        )

        target_url = f"{instance.url.rstrip('/')}{request.url.path}"
        if request.url.query:
            target_url = f"{target_url}?{request.url.query}"

        headers = dict(request.headers)
        headers.pop("host", None)

        body = await request.body()

        http_client = await self._get_http_client()

        try:
            response = await http_client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

            response_headers = dict(response.headers)
            response_headers.pop("content-encoding", None)
            response_headers.pop("content-length", None)
            response_headers.pop("transfer-encoding", None)

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers,
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout proxying to {target_url}")
            return Response(
                content=b'{"error": "Gateway timeout"}',
                status_code=504,
                media_type="application/json",
            )
        except httpx.RequestError as e:
            logger.error(f"Error proxying to {target_url}: {e}")
            return Response(
                content=b'{"error": "Bad gateway"}',
                status_code=502,
                media_type="application/json",
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI application entry point."""
        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
            return

        if scope["type"] != "http":
            return

        await self._startup()

        request = Request(scope, receive, send)

        if request.url.path == "/health":
            response = Response(
                content=b'{"status": "healthy"}',
                status_code=200,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return

        match = self._match_route(request.url.path, request.method)

        if match is None:
            response = Response(
                content=b'{"error": "Not found"}',
                status_code=404,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return

        service, _ = match

        try:
            response = await self._proxy_request(request, service)
            await response(scope, receive, send)
        except NoHealthyInstanceError:
            response = Response(
                content=b'{"error": "Service unavailable"}',
                status_code=503,
                media_type="application/json",
            )
            await response(scope, receive, send)

    async def _handle_lifespan(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Handle ASGI lifespan events."""
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                try:
                    await self._startup()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as e:
                    await send({
                        "type": "lifespan.startup.failed",
                        "message": str(e),
                    })
                    return

            elif message["type"] == "lifespan.shutdown":
                await self._shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return
