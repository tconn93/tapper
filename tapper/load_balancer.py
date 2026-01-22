"""Load balancing strategies for service instances."""

import random
from abc import ABC, abstractmethod
from collections import defaultdict

from tapper.exceptions import NoHealthyInstanceError
from tapper.models import ServiceInstance


class LoadBalancer(ABC):
    """Abstract base class for load balancing strategies."""

    @abstractmethod
    def select_instance(
        self,
        instances: list[ServiceInstance],
        service_name: str = "",
    ) -> ServiceInstance:
        """Select an instance from the list of available instances.

        Args:
            instances: List of available service instances.
            service_name: Name of the service (for stateful balancers).

        Returns:
            The selected instance.

        Raises:
            NoHealthyInstanceError: If no healthy instances are available.
        """
        pass

    def _filter_healthy(self, instances: list[ServiceInstance]) -> list[ServiceInstance]:
        """Filter to only healthy instances."""
        return [inst for inst in instances if inst.healthy]


class RoundRobinBalancer(LoadBalancer):
    """Round-robin load balancing strategy.

    Distributes requests evenly across all healthy instances.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)

    def select_instance(
        self,
        instances: list[ServiceInstance],
        service_name: str = "",
    ) -> ServiceInstance:
        healthy = self._filter_healthy(instances)
        if not healthy:
            raise NoHealthyInstanceError(service_name)

        index = self._counters[service_name] % len(healthy)
        self._counters[service_name] += 1
        return healthy[index]


class RandomBalancer(LoadBalancer):
    """Random load balancing strategy.

    Randomly selects from healthy instances.
    """

    def select_instance(
        self,
        instances: list[ServiceInstance],
        service_name: str = "",
    ) -> ServiceInstance:
        healthy = self._filter_healthy(instances)
        if not healthy:
            raise NoHealthyInstanceError(service_name)

        return random.choice(healthy)


class LeastConnectionsBalancer(LoadBalancer):
    """Least connections load balancing strategy.

    Selects the instance with the fewest active connections.
    Note: Requires external connection tracking.
    """

    def __init__(self) -> None:
        self._connections: dict[str, int] = defaultdict(int)

    def select_instance(
        self,
        instances: list[ServiceInstance],
        service_name: str = "",
    ) -> ServiceInstance:
        healthy = self._filter_healthy(instances)
        if not healthy:
            raise NoHealthyInstanceError(service_name)

        min_connections = float("inf")
        selected = healthy[0]

        for inst in healthy:
            conn_count = self._connections[inst.url]
            if conn_count < min_connections:
                min_connections = conn_count
                selected = inst

        return selected

    def increment(self, url: str) -> None:
        """Increment the connection count for an instance."""
        self._connections[url] += 1

    def decrement(self, url: str) -> None:
        """Decrement the connection count for an instance."""
        if self._connections[url] > 0:
            self._connections[url] -= 1


def get_load_balancer(strategy: str | LoadBalancer) -> LoadBalancer:
    """Get a load balancer instance by name or return the provided instance.

    Args:
        strategy: Either a LoadBalancer instance or a string name
                 ("round-robin", "random", "least-connections").

    Returns:
        A LoadBalancer instance.

    Raises:
        ValueError: If the strategy name is unknown.
    """
    if isinstance(strategy, LoadBalancer):
        return strategy

    strategies = {
        "round-robin": RoundRobinBalancer,
        "random": RandomBalancer,
        "least-connections": LeastConnectionsBalancer,
    }

    if strategy not in strategies:
        raise ValueError(
            f"Unknown load balancer strategy: {strategy}. "
            f"Available: {list(strategies.keys())}"
        )

    return strategies[strategy]()
