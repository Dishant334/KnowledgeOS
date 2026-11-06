"""
CORS (app/core/cors.py): the browser frontend must be able to call the API from its own origin.

A preflight is the browser's "may I?" request (an OPTIONS call with no token) sent before a call with an
Authorization header; the API must answer it itself. These tests use the real app and an origin from the
default setting (http://localhost:5173).
"""

import pytest

from app.core.cors import EXPOSED_HEADERS, cors_options, parse_origins

FRONTEND = "http://localhost:5173"


def lowered(response) -> dict:
    return {key.lower(): value for key, value in response.headers.items()}


def test_the_preflight_for_the_streaming_endpoint_is_answered_without_a_token(client):
    response = client.options("/ask/stream", headers={
        "Origin": FRONTEND,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })

    headers = lowered(response)
    assert response.status_code == 200
    assert headers["access-control-allow-origin"] == FRONTEND
    assert "POST" in headers["access-control-allow-methods"]
    assert "authorization" in headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in headers          # tokens travel in a header, not cookies


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_the_preflight_allows_the_conversation_management_methods(client, method):
    response = client.options("/conversations/1", headers={
        "Origin": FRONTEND, "Access-Control-Request-Method": method, "Access-Control-Request-Headers": "authorization",
    })
    assert response.status_code == 200 and method in lowered(response)["access-control-allow-methods"]


def test_real_responses_expose_the_headers_the_frontend_needs_to_read(client):
    headers = lowered(client.get("/health", headers={"Origin": FRONTEND}))

    assert headers["access-control-allow-origin"] == FRONTEND
    exposed = {name.strip().lower() for name in headers["access-control-expose-headers"].split(",")}
    assert {name.lower() for name in EXPOSED_HEADERS} <= exposed        # Retry-After, X-RateLimit-*


def test_error_responses_carry_cors_headers_too(client):
    """Otherwise the browser hides a 401 or 429 from the page and the UI can only say 'network error'."""
    response = client.post("/ask", headers={"Origin": FRONTEND}, json={"query": "hi"})

    assert response.status_code == 401
    assert lowered(response)["access-control-allow-origin"] == FRONTEND


def test_an_origin_that_is_not_listed_gets_no_cors_headers(client):
    evil = "https://evil.example"

    simple = client.get("/health", headers={"Origin": evil})
    assert "access-control-allow-origin" not in lowered(simple)

    preflight = client.options("/ask", headers={"Origin": evil, "Access-Control-Request-Method": "POST"})
    assert preflight.status_code == 400 and "access-control-allow-origin" not in lowered(preflight)


# --- the settings helpers (no app needed) ----------------------------------------------------------------


@pytest.mark.parametrize("value, expected", [
    ("http://localhost:5173", ["http://localhost:5173"]),
    (" http://a.com , http://b.com/ ", ["http://a.com", "http://b.com"]),     # spaces and trailing slashes tidied
    ("http://a.com,,", ["http://a.com"]),
    ("", []),
    ("   ", []),
])
def test_parse_origins(value, expected):
    assert parse_origins(value) == expected


def test_an_empty_setting_turns_cors_off_and_a_real_one_never_allows_credentials():
    assert cors_options("") is None
    options = cors_options("http://localhost:5173")
    assert options["allow_origins"] == ["http://localhost:5173"] and options["allow_credentials"] is False
