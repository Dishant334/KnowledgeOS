from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.clerk import ClerkTokenError, ClerkUnavailableError, verify_clerk_token
from app.db.database import get_db
from app.db.models.user import User
from app.services.auth import get_or_create_user


security = HTTPBearer()

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:

    token = credentials.credentials

    # 1. Verify Clerk JWT
    try:
        payload = verify_clerk_token(token)
    except ClerkUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except ClerkTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Clerk token",
            headers=_UNAUTHORIZED_HEADERS,
        )

    # 2. Get Clerk user ID (verify_clerk_token requires `sub`; guard anyway)
    clerk_user_id = payload.get("sub")

    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk user ID missing from token",
            headers=_UNAUTHORIZED_HEADERS,
        )

    # 3. Map to the local PostgreSQL user. The Clerk webhook is the primary
    #    sync path; if it hasn't arrived yet (or isn't configured, e.g. local
    #    dev), provision a minimal row from the verified identity.
    return get_or_create_user(db, clerk_user_id)
