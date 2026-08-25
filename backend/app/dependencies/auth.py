from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.clerk import verify_clerk_token
from app.db.database import get_db
from app.db.models.user import User


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:

    token = credentials.credentials

    # 1. Verify Clerk JWT
    try:
        payload = verify_clerk_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Clerk token",
        )

    # 2. Get Clerk user ID
    clerk_user_id = payload.get("sub")

    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk user ID missing from token",
        )

    # 3. Find local PostgreSQL user
    user = (
        db.query(User)
        .filter(User.clerk_user_id == clerk_user_id)
        .first()
    )

    # 4. User must exist in our database
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user