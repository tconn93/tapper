from tapper import TapperGateway

gateway = TapperGateway(registry_url="http://localhost:8001",
 discovery_interval=15,
 load_balancer="round-robin")