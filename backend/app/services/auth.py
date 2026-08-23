from sqlalchemy.orm import Session
from app.db.models.user import User


def get_user_by_clerk_id(db: Session, clerk_user_id: str) -> User | None:
    return db.query(User).filter_by(clerk_user_id=clerk_user_id).first()


def create_user(db: Session, clerk_user_id: str, email: str) -> User:
    user = User(clerk_user_id=clerk_user_id, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def upsert_user_from_clerk_event(db: Session, clerk_user_id: str, email: str) -> User:
    user = get_user_by_clerk_id(db, clerk_user_id)
    if user is None:
        return create_user(db, clerk_user_id, email)
    if user.email != email:
        user.email = email
        db.commit()
        db.refresh(user)
    return user


def delete_user_by_clerk_id(db: Session, clerk_user_id: str) -> None:
    user = get_user_by_clerk_id(db, clerk_user_id)
    if user:
        db.delete(user)
        db.commit()