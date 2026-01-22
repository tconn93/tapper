"""Tapper - A microservices framework for FastAPI.

Tapper provides service discovery and API gateway routing for FastAPI applications.

Quick Start:
    # Register a service
    from fastapi import FastAPI
    from tapper import Service

    @Service(name="user-service", version="1.0.0")
    app = FastAPI()

    # Create a gateway
    from tapper import TapperGateway

    gateway = TapperGateway(registry_url="http://localhost:8001")

    # Run with uvicorn
    # uvicorn gateway:gateway --port 8000

Example:
    See the README for full usage examples.
"""

from tapper.exceptions import (
    LoadBalancerError,
    NoHealthyInstanceError,
    RegistryError,
    ServiceNotFoundError,
    TapperException,
)
from tapper.gateway import TapperGateway
from tapper.load_balancer import (
    LeastConnectionsBalancer,
    LoadBalancer,
    RandomBalancer,
    RoundRobinBalancer,
)
from tapper.models import Route, ServiceInfo, ServiceInstance
from tapper.registry import RegistryBackend
from tapper.service import Service

__version__ = "0.1.0"

__all__ = [
    # Core
    "Service",
    "TapperGateway",
    # Load Balancing
    "LoadBalancer",
    "RoundRobinBalancer",
    "RandomBalancer",
    "LeastConnectionsBalancer",
    # Models
    "ServiceInfo",
    "ServiceInstance",
    "Route",
    # Registry
    "RegistryBackend",
    # Exceptions
    "TapperException",
    "RegistryError",
    "ServiceNotFoundError",
    "NoHealthyInstanceError",
    "LoadBalancerError",
]
