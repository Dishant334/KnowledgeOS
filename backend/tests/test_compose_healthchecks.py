"""
The api and worker services in docker-compose.yml must have health checks that really test them
(static checks of the file: no Docker needed, about a second). The real behaviour (healthy, then
unhealthy when the process dies) was verified once against a running isolated compose project.
"""

import re
from pathlib import Path

import pytest
import yaml

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


@pytest.fixture(scope="module")
def services() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))["services"]


def seconds(value: str) -> int:
    assert re.fullmatch(r"\d+s", value), f"expected a duration like '15s', got {value!r}"
    return int(value[:-1])


@pytest.mark.parametrize("name", ["api", "worker"])
def test_service_has_a_complete_healthcheck(services, name):
    check = services[name]["healthcheck"]

    assert check["test"] and {"interval", "timeout", "retries", "start_period"} <= set(check)
    assert check["retries"] >= 1
    assert seconds(check["timeout"]) < seconds(check["interval"])      # a check must finish before the next one starts
    assert seconds(check["start_period"]) > 0                          # grace time while the service boots


def test_api_check_calls_the_real_health_route_on_the_published_port(services):
    from app.main import app

    check = " ".join(services["api"]["healthcheck"]["test"])
    assert "curl" in check and "-fsS" in check                                 # -f: an HTTP error status must fail the check
    assert "localhost:8000/health" in check
    assert "8000:8000" in services["api"]["ports"]
    assert "/health" in {getattr(route, "path", None) for route in app.routes}    # the route it calls really exists


def test_worker_check_pings_the_same_celery_app_the_worker_runs(services):
    command = services["worker"]["command"]
    check = services["worker"]["healthcheck"]["test"][-1]

    app_module = re.search(r"-A (\S+)", command).group(1)
    assert f"-A {app_module}" in check and "inspect ping" in check
    assert "celery@$$HOSTNAME" in check                                       # the node name; $$ keeps compose from expanding it
    assert "grep -q pong" in check                                            # no reply means unhealthy


def test_nothing_else_lost_its_healthcheck(services):
    for name in ("postgres", "qdrant", "redis"):
        assert services[name]["healthcheck"]["test"]
