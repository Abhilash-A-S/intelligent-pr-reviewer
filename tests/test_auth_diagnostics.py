import logging

import httpx
import pytest
from starlette.requests import Request

from pr_reviewer.web.security import log_sign_in_failure
from test_provider_login import setup as provider_fixture, start

setup = provider_fixture


def test_token_failure_logs_category_and_numeric_code_without_payload(caplog):
    request = httpx.Request("POST", "https://identity.example/token?code=SECRET_CODE")
    response = httpx.Response(
        400,
        request=request,
        json={
            "error": "invalid_client",
            "error_codes": [7000215],
            "error_description": "AADSTS7000215: SECRET_SECRET invalid secret",
            "access_token": "SECRET_TOKEN",
        },
    )
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        log_sign_in_failure(
            "microsoft",
            "token_exchange",
            httpx.HTTPStatusError(
                "SECRET_EXCEPTION", request=request, response=response
            ),
        )
    assert "stage=token_exchange" in caplog.text
    assert "http_status=400" in caplog.text
    assert "oauth_error=invalid_client" in caplog.text
    assert "provider_codes=7000215" in caplog.text
    assert "SECRET" not in caplog.text
    assert "identity.example" not in caplog.text


@pytest.mark.parametrize(
    "payload", [[], None, {"error": ["SECRET"]}, {"error_codes": "SECRET"}]
)
def test_unexpected_provider_body_does_not_break_diagnostics(caplog, payload):
    request = httpx.Request("POST", "https://identity.example/token")
    response = httpx.Response(400, request=request, json=payload)
    log_sign_in_failure(
        "microsoft",
        "token_exchange",
        httpx.HTTPStatusError("SECRET", request=request, response=response),
    )
    assert "Sign-in failed:" in caplog.text
    assert "SECRET" not in caplog.text


def test_callback_query_logs_only_allowlisted_error_and_numeric_code(caplog):
    request = Request(
        {
            "type": "http",
            "query_string": (
                b"error=access_denied&error_description=AADSTS65001%3A%20SECRET&code=SECRET&state=SECRET"
            ),
        }
    )
    log_sign_in_failure(
        "microsoft", "callback_validation", ValueError("SECRET"), request
    )
    assert "oauth_error=access_denied" in caplog.text
    assert "provider_codes=65001" in caplog.text
    assert "SECRET" not in caplog.text


def test_unknown_error_and_exception_message_never_logged(caplog):
    request = Request({"type": "http", "query_string": b"error=SECRET%0Aforged"})
    log_sign_in_failure("github", "callback_validation", ValueError("SECRET"), request)
    assert "SECRET" not in caplog.text
    assert "forged" not in caplog.text


def test_missing_delegated_token_has_useful_safe_field(caplog):
    log_sign_in_failure("microsoft", "azure_delegated_token", KeyError("access_token"))
    assert "missing_field=access_token" in caplog.text


def test_real_callback_failure_logs_stage_and_keeps_generic_redirect(setup, caplog):
    auth, client, _ = setup
    auth._metadata = {
        "authorization_endpoint": "https://identity.example/authorize",
        "token_endpoint": "https://identity.example/token",
    }
    _, query = start(client, "microsoft")
    response = client.get(
        "/api/auth/callback",
        params={
            "state": query["state"][0],
            "error": "access_denied",
            "error_description": "AADSTS65001: SECRET",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=sign_in_failed"
    assert "stage=callback_validation" in caplog.text
    assert "provider_codes=65001" in caplog.text
    assert "SECRET" not in caplog.text
