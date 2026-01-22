"""Command-line interface for Tapper."""

import click
import uvicorn

from tapper.registry.backends import InMemoryBackend, RegistryBackend


def get_backend(backend_type: str, redis_url: str | None) -> RegistryBackend:
    """Create a registry backend based on the specified type."""
    if backend_type == "memory":
        return InMemoryBackend()
    elif backend_type == "redis":
        try:
            from tapper.registry.backends.redis import RedisBackend
        except ImportError:
            raise click.ClickException(
                "Redis backend requires the 'redis' package. "
                "Install with: pip install tapper[redis]"
            )
        url = redis_url or "redis://localhost:6379"
        return RedisBackend(redis_url=url)
    else:
        raise click.ClickException(f"Unknown backend type: {backend_type}")


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """Tapper - A microservices framework for FastAPI."""
    pass


@main.command()
@click.option(
    "--host",
    default="0.0.0.0",
    help="Host to bind the server to",
)
@click.option(
    "--port",
    default=8001,
    type=int,
    help="Port to bind the server to",
)
@click.option(
    "--backend",
    default="memory",
    type=click.Choice(["memory", "redis"]),
    help="Storage backend for the registry",
)
@click.option(
    "--redis-url",
    default=None,
    help="Redis URL (only used with redis backend)",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload for development",
)
@click.option(
    "--cleanup-interval",
    default=30,
    type=int,
    help="Seconds between stale instance cleanup",
)
@click.option(
    "--stale-threshold",
    default=60,
    type=int,
    help="Seconds after which an instance is considered stale",
)
def registry(
    host: str,
    port: int,
    backend: str,
    redis_url: str | None,
    reload: bool,
    cleanup_interval: int,
    stale_threshold: int,
) -> None:
    """Run the Tapper service registry server."""
    click.echo(f"Starting Tapper registry on {host}:{port}")
    click.echo(f"Backend: {backend}")

    if reload:
        uvicorn.run(
            "tapper.registry.server:create_registry_app",
            factory=True,
            host=host,
            port=port,
            reload=reload,
        )
    else:
        from tapper.registry.server import create_registry_app

        backend_instance = get_backend(backend, redis_url)
        app = create_registry_app(
            backend=backend_instance,
            cleanup_interval=cleanup_interval,
            stale_threshold=stale_threshold,
        )
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
