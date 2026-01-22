
# Tapper - Python Microservices Framework

[![PyPI version](https://badge.fury.io/py/tapper.svg)](https://badge.fury.io/py/tapper)
[![Python Versions](https://img.shields.io/pypi/pyversions/tapper.svg)](https://pypi.org/project/tapper/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Tapper** is a lightweight, elegant Python framework that simplifies **service discovery** and **API gateway routing** for **FastAPI**-based microservices.

With a single `@Service` decorator placed on your service's `main.py`, Tapper automatically registers your service and provides a powerful **API gateway** that discovers all services and intelligently routes requests to the correct backend.

## Features

- **Zero-boilerplate registration** with `@tapper.Service`
- **Automatic service discovery** and registration
- **Built-in dynamic API gateway** with path-based routing
- **Transparent proxying** of requests (path params, query strings, headers, body)
- **Health checks** and service status monitoring
- **Load balancing** (round-robin by default)
- **Seamless integration** with existing FastAPI apps
- **Minimal configuration** — focus on your business logic

## Installation

```bash
pip install tapper
```

## Quick Start

### 1. Annotate Your Service (in `main.py` of each microservice)

```python
from fastapi import FastAPI
from tapper import Service

app = FastAPI()

@Service(name="user-service", version="1.0.0", description="User management service")
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"user_id": user_id, "name": "Jane Doe"}

@app.post("/users/")
async def create_user(user: dict):
    return {"message": "User created", "user": user}
```

That's all! The `@Service` decorator registers your service automatically.

### 2. Run the API Gateway

Create a separate gateway application (e.g., `gateway.py`):

```python
from fastapi import FastAPI
from tapper import TapperGateway

app = FastAPI(title="Tapper API Gateway")

# Initialize the gateway (you can pass registry_url or use env vars)
gateway = TapperGateway()

# Mount the gateway at the root
app.mount("/", gateway)

# Optional: expose gateway health
@app.get("/health")
async def health():
    return {"status": "healthy", "services": gateway.get_service_status()}
```

Run it:

```bash
uvicorn gateway:app --port 8000
```

Now your gateway at `http://localhost:8000` will automatically discover and route to all `@Service`-decorated FastAPI apps.

## How It Works

1. Each microservice uses the `@Service` decorator on its `FastAPI` instance.
2. Tapper registers the service (name, version, endpoints) with a central registry.
3. The **TapperGateway** periodically discovers available services.
4. Incoming requests are matched against registered service routes.
5. Requests are proxied transparently to the correct service instance.

## Configuration Options

### Service Decorator

```python
@Service(
    name="payment-service",
    version="2.1.0",
    description="Handles all payment operations",
    prefix="/payments",           # optional: prefix all routes
    health_endpoint="/health",    # optional: custom health check path
    tags=["payments", "finance"]  # optional: OpenAPI tags
)
```

### Gateway Configuration

```python
gateway = TapperGateway(
    registry_url="http://registry:8001",   # or via TAPER_REGISTRY_URL env var
    discovery_interval=30,                 # seconds
    timeout=5,                             # request timeout in seconds
    load_balancer="round-robin",           # or "random", "least-connections", custom
    # auth_provider=YourAuthProvider(),    # optional
)
```

## Advanced Usage

### Custom Load Balancer

```python
from tapper import LoadBalancer

class CustomBalancer(LoadBalancer):
    def select_instance(self, instances):
        # Your custom logic
        return instances[0]

gateway = TapperGateway(load_balancer=CustomBalancer())
```

### Supported Registries

- In-memory (development)
- Redis
- Consul
- etcd
- Custom backend (extend `tapper.registry.RegistryBackend`)

## Contributing

Contributions are welcome!

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.

## Acknowledgments

- Built on the amazing [FastAPI](https://fastapi.tiangolo.com/)
- Inspired by service discovery patterns from Kubernetes, Consul, and Spring Cloud

---

Happy microservicing with **Tapper**! 🚀
```

Feel free to customize badges, add a real logo, or adjust the configuration details as you implement the actual framework!