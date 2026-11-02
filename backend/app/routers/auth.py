import json

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError

from app.dependencies.auth import get_current_user
from app.db.database import get_db
from app.core.config import settings
from app.schemas.user import UserOut
from app.services.auth import upsert_user_from_clerk_event, delete_user_by_clerk_id
from app.db.models.user import User

router = APIRouter()


@router.get("/users/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


def _primary_email(data: dict) -> str | None:
    """Clerk lists all addresses; the primary one is referenced by id."""
    addresses = data.get("email_addresses") or []
    primary_id = data.get("primary_email_address_id")
    for address in addresses:
        if address.get("id") == primary_id:
            return address.get("email_address") or None
    return (addresses[0].get("email_address") or None) if addresses else None


def _full_name(data: dict) -> str | None:
    parts = [data.get("first_name"), data.get("last_name")]
    return " ".join(p for p in parts if p) or None


@router.post("/webhooks/clerk", status_code=200)
async def clerk_webhook(request: Request, db: Session = Depends(get_db)):
    if not settings.clerk_webhook_secret:
        raise HTTPException(status_code=503, detail="Clerk webhook secret not configured")

    payload = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }

    try:
        # svix>=2 verify() returns None (raises on failure), so parse the
        # body ourselves only AFTER the signature has been verified.
        Webhook(settings.clerk_webhook_secret).verify(payload, headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        event = json.loads(payload)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event_type = event.get("type")
    data = event.get("data") or {}

    if event_type in ("user.created", "user.updated", "user.deleted"):
        clerk_user_id = data.get("id")
        if not clerk_user_id:
            raise HTTPException(status_code=400, detail="Webhook payload missing user id")

        if event_type == "user.deleted":
            delete_user_by_clerk_id(db, clerk_user_id)
        else:
            upsert_user_from_clerk_event(
                db,
                clerk_user_id,
                email=_primary_email(data),
                name=_full_name(data),
            )

    return {"received": True}
