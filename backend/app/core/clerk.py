import jwt
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError

from app.core.config import settings


class ClerkTokenError(Exception):
    """Token is missing, malformed, unsigned by Clerk, expired, or otherwise invalid."""


class ClerkUnavailableError(Exception):
    """Clerk's JWKS endpoint couldn't be reached — a server-side problem, not the caller's."""


# PyJWKClient caches the JWKS (and re-fetches on unknown `kid`, which covers key rotation).
_jwk_client = PyJWKClient(settings.clerk_jwks_url)

# Small tolerance for clock skew between Clerk and this server.
_LEEWAY_SECONDS = 5


def _authorized_parties() -> set[str]:
    return {p.strip() for p in settings.clerk_authorized_parties.split(",") if p.strip()}


def verify_clerk_token(token: str) -> dict:
    """
    Verifies a Clerk session JWT and returns its claims ("sub" = Clerk user ID).

    Enforced: RS256 signature against Clerk's JWKS, issuer, exp/nbf (with
    leeway), presence of exp/iat/iss/sub, and — when CLERK_AUTHORIZED_PARTIES
    is configured — the `azp` claim. Clerk session tokens carry no `aud`.
    """
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError as exc:  # subclass of PyJWKClientError: check first
        raise ClerkUnavailableError("Unable to fetch Clerk JWKS") from exc
    except (PyJWKClientError, jwt.InvalidTokenError) as exc:
        raise ClerkTokenError("Unable to resolve signing key") from exc

    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            leeway=_LEEWAY_SECONDS,
            options={
                "require": ["exp", "iat", "iss", "sub"],
                "verify_aud": False,
            },
        )
    except jwt.InvalidTokenError as exc:
        raise ClerkTokenError(str(exc)) from exc

    parties = _authorized_parties()
    if parties and payload.get("azp") not in parties:
        raise ClerkTokenError("Token issued for an unauthorized party")

    return payload
