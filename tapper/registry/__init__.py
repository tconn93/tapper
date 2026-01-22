"""Registry module for service discovery."""

from tapper.registry.backends import InMemoryBackend, RegistryBackend
from tapper.registry.client import RegistryClient
from tapper.registry.server import create_registry_app

__all__ = [
    "RegistryBackend",
    "InMemoryBackend",
    "RegistryClient",
    "create_registry_app",
]

try:
    from tapper.registry.backends import RedisBackend
    __all__.append("RedisBackend")
except ImportError:
    pass
