"""Custom exceptions for the Tapper framework."""


class TapperException(Exception):
    """Base exception for all Tapper-related errors."""

    pass


class RegistryError(TapperException):
    """Raised when there's an error communicating with the registry."""

    pass


class ServiceNotFoundError(TapperException):
    """Raised when a requested service is not found in the registry."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"Service not found: {service_name}")


class NoHealthyInstanceError(TapperException):
    """Raised when no healthy instances are available for a service."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"No healthy instances available for service: {service_name}")


class LoadBalancerError(TapperException):
    """Raised when there's an error in load balancer selection."""

    pass
