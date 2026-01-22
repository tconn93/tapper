"""Tests for the Service decorator."""

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from tapper.models import Route
from tapper.service import Service, _extract_routes


class TestExtractRoutes:
    """Tests for route extraction from FastAPI apps."""

    def test_extract_basic_routes(self, test_fastapi_app):
        routes = _extract_routes(test_fastapi_app)

        assert len(routes) >= 3  # users list, get, create + health
        paths = {r.path for r in routes}
        assert "/users" in paths
        assert "/users/{user_id}" in paths

    def test_extract_routes_with_prefix(self, test_fastapi_app):
        routes = _extract_routes(test_fastapi_app, prefix="/api")

        paths = {r.path for r in routes}
        assert "/api/users" in paths
        assert "/api/users/{user_id}" in paths

    def test_extract_routes_includes_methods(self, test_fastapi_app):
        routes = _extract_routes(test_fastapi_app)

        # FastAPI creates separate route objects per endpoint,
        # so collect all methods across routes with the same path
        users_routes = [r for r in routes if r.path == "/users"]
        all_methods = set()
        for r in users_routes:
            all_methods.update(r.methods)

        assert "GET" in all_methods
        assert "POST" in all_methods


class TestServiceDecorator:
    """Tests for the Service decorator."""

    def test_decorator_preserves_app(self, test_fastapi_app):
        decorated = Service(name="test", version="1.0.0")(test_fastapi_app)

        assert decorated is test_fastapi_app
        assert isinstance(decorated, FastAPI)

    def test_decorator_sets_lifespan(self, test_fastapi_app):
        original_lifespan = test_fastapi_app.router.lifespan_context

        Service(name="test", version="1.0.0")(test_fastapi_app)

        assert test_fastapi_app.router.lifespan_context is not original_lifespan

    def test_decorator_stores_configuration(self):
        service = Service(
            name="my-service",
            version="2.0.0",
            description="Test service",
            prefix="/api",
            health_endpoint="/healthz",
            tags=["tag1", "tag2"],
        )

        assert service.name == "my-service"
        assert service.version == "2.0.0"
        assert service.description == "Test service"
        assert service.prefix == "/api"
        assert service.health_endpoint == "/healthz"
        assert service.tags == ["tag1", "tag2"]

    def test_get_instance_url_with_explicit_url(self):
        service = Service(
            name="test",
            version="1.0.0",
            url="http://myhost:9000",
        )

        assert service._get_instance_url() == "http://myhost:9000"

    def test_get_instance_url_default(self, monkeypatch):
        monkeypatch.delenv("UVICORN_HOST", raising=False)
        monkeypatch.delenv("UVICORN_PORT", raising=False)
        monkeypatch.delenv("HOST", raising=False)
        monkeypatch.delenv("PORT", raising=False)

        service = Service(name="test", version="1.0.0")

        assert service._get_instance_url() == "http://127.0.0.1:8000"

    def test_get_instance_url_from_env(self, monkeypatch):
        monkeypatch.setenv("HOST", "192.168.1.100")
        monkeypatch.setenv("PORT", "3000")

        service = Service(name="test", version="1.0.0")

        assert service._get_instance_url() == "http://192.168.1.100:3000"

    def test_get_instance_url_replaces_0000(self, monkeypatch):
        monkeypatch.setenv("HOST", "0.0.0.0")
        monkeypatch.setenv("PORT", "8080")

        service = Service(name="test", version="1.0.0")

        assert service._get_instance_url() == "http://127.0.0.1:8080"
