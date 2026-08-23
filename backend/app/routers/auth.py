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


@router.post("/webhooks/clerk", status_code=200)
async def clerk_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id"),
        "svix-timestamp": request.headers.get("svix-timestamp"),
        "svix-signature": request.headers.get("svix-signature"),
    }

    try:
        wh = Webhook(settings.clerk_webhook_secret)
        event = wh.verify(payload, headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("type")
    data = event.get("data", {})

    if event_type == "user.created" or event_type == "user.updated":
        clerk_user_id = data["id"]
        email_addresses = data.get("email_addresses", [])
        email = email_addresses[0]["email_address"] if email_addresses else ""
        upsert_user_from_clerk_event(db, clerk_user_id, email)

    elif event_type == "user.deleted":
        clerk_user_id = data.get("id")
        if clerk_user_id:
            delete_user_by_clerk_id(db, clerk_user_id)

    return {"received": True}