"""Pydantic models for the Tapper framework."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Route(BaseModel):
    """Represents an API route exposed by a service."""

    path: str = Field(..., description="Route path pattern, e.g., '/users/{user_id}'")
    methods: list[str] = Field(..., description="HTTP methods, e.g., ['GET', 'POST']")


class ServiceInstance(BaseModel):
    """Represents a running instance of a service."""

    url: str = Field(..., description="Base URL of the instance, e.g., 'http://localhost:8001'")
    health_endpoint: str = Field(default="/health", description="Health check endpoint path")
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(UTC))
    healthy: bool = Field(default=True)


class ServiceInfo(BaseModel):
    """Complete information about a registered service."""

    name: str = Field(..., description="Unique service name")
    version: str = Field(..., description="Service version")
    description: str | None = Field(default=None)
    prefix: str | None = Field(default=None, description="URL prefix for routing")
    routes: list[Route] = Field(default_factory=list)
    instances: list[ServiceInstance] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RegisterRequest(BaseModel):
    """Request body for service registration."""

    service: ServiceInfo
    instance: ServiceInstance


class HeartbeatRequest(BaseModel):
    """Request body for heartbeat updates."""

    instance_url: str


class UnregisterRequest(BaseModel):
    """Request body for service unregistration."""

    name: str
    instance_url: str
