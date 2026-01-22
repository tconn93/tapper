"""Registry backend implementations."""

from tapper.registry.backends.base import RegistryBackend
from tapper.registry.backends.memory import InMemoryBackend

__all__ = ["RegistryBackend", "InMemoryBackend"]

try:
    from tapper.registry.backends.redis import RedisBackend
    __all__.append("RedisBackend")
except ImportError:
    pass
