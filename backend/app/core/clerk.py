import jwt
from jwt import PyJWKClient
from app.core.config import settings

_jwk_client= PyJWKClient(settings.clerk_jwks_url)

def verify_clerk_token(token: str) -> dict:
    signing_key = _jwk_client.get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=settings.clerk_issuer,
        options={"verify_aud": False},  # Clerk session tokens don't set aud by default
    )
    return payload  # contains "sub" = clerk_user_id, plus session claims