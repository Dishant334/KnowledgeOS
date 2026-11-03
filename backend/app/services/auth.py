from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.memory.store import delete_all_memories

# All writes go through INSERT ... ON CONFLICT on the unique users.clerk_user_id
# index, so concurrent/duplicate webhook deliveries and the first authenticated
# request racing a webhook can never create duplicate rows or raise
# unique-violation errors.


def get_user_by_clerk_id(db: Session, clerk_user_id: str) -> User | None:
    return db.query(User).filter_by(clerk_user_id=clerk_user_id).first()


def get_or_create_user(db: Session, clerk_user_id: str) -> User:
    """
    Resolve a verified Clerk identity to the local user, provisioning a
    minimal row if the user.created webhook hasn't arrived yet. The webhook
    later fills in email/name via upsert_user_from_clerk_event.
    """
    user = get_user_by_clerk_id(db, clerk_user_id)
    if user is not None:
        return user

    db.execute(
        insert(User)
        .values(clerk_user_id=clerk_user_id, created_at=func.now(), updated_at=func.now())
        .on_conflict_do_nothing(index_elements=[User.clerk_user_id])
    )
    db.commit()
    return get_user_by_clerk_id(db, clerk_user_id)


def upsert_user_from_clerk_event(
    db: Session,
    clerk_user_id: str,
    email: str | None,
    name: str | None = None,
) -> User:
    stmt = insert(User).values(
        clerk_user_id=clerk_user_id,
        email=email,
        name=name,
        created_at=func.now(),
        updated_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[User.clerk_user_id],
        set_={"email": stmt.excluded.email, "name": stmt.excluded.name, "updated_at": func.now()},
    )
    db.execute(stmt)
    db.commit()
    user = get_user_by_clerk_id(db, clerk_user_id)
    db.refresh(user)
    return user


def delete_user_by_clerk_id(db: Session, clerk_user_id: str) -> None:
    user = get_user_by_clerk_id(db, clerk_user_id)
    if user:
        # Long-term memory lives outside the users table (no cascade), so delete it
        # explicitly. If this fails the webhook errors and Clerk retries, instead of
        # silently leaving a deleted user's personal facts behind.
        delete_all_memories(user.id)
        db.delete(user)
        db.commit()
