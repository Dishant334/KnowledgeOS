"""Clerk → backend webhook: svix signature verification and user sync."""

import json
import uuid
from datetime import datetime, timedelta, timezone

from svix.webhooks import Webhook

from app.db.models.conversation import Conversation
from app.db.models.user import User
from tests.conftest import TEST_WEBHOOK_SECRET, unique_clerk_id

URL = "/webhooks/clerk"


def _signed(payload: dict, *, secret: str = TEST_WEBHOOK_SECRET, msg_id: str | None = None, at=None):
    body = json.dumps(payload)
    msg_id = msg_id or f"msg_{uuid.uuid4().hex}"
    at = at or datetime.now(timezone.utc)
    sig = Webhook(secret).sign(msg_id, at, body)
    headers = {
        "svix-id": msg_id,
        "svix-timestamp": str(int(at.timestamp())),
        "svix-signature": sig,
        "content-type": "application/json",
    }
    return body, headers


def _user_event(event_type: str, clerk_id: str, *, emails=("alice@example.com",), primary_index=0,
                first="Alice", last="Smith"):
    email_objs = [{"id": f"idn_{i}", "email_address": e} for i, e in enumerate(emails)]
    return {
        "type": event_type,
        "object": "event",
        "data": {
            "id": clerk_id,
            "object": "user",
            "email_addresses": email_objs,
            "primary_email_address_id": email_objs[primary_index]["id"] if email_objs else None,
            "first_name": first,
            "last_name": last,
        },
    }


def _post(client, payload, **kw):
    body, headers = _signed(payload, **kw)
    return client.post(URL, content=body, headers=headers)


# --- Signature verification ------------------------------------------------


def test_missing_svix_headers_400(client):
    assert client.post(URL, json=_user_event("user.created", unique_clerk_id())).status_code == 400


def test_invalid_signature_400(client, db):
    cid = unique_clerk_id()
    body, headers = _signed(_user_event("user.created", cid))
    headers["svix-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    assert client.post(URL, content=body, headers=headers).status_code == 400
    assert db.query(User).filter_by(clerk_user_id=cid).count() == 0


def test_signed_with_wrong_secret_400(client, db):
    cid = unique_clerk_id()
    other = "whsec_" + "QUJDREVGR0hJSktMTU5PUFFSU1RVVldY"
    assert _post(client, _user_event("user.created", cid), secret=other).status_code == 400
    assert db.query(User).filter_by(clerk_user_id=cid).count() == 0


def test_tampered_body_400(client, db):
    cid = unique_clerk_id()
    body, headers = _signed(_user_event("user.created", cid))
    tampered = body.replace("alice@example.com", "mallory@example.com")
    assert client.post(URL, content=tampered, headers=headers).status_code == 400


def test_stale_timestamp_400(client):
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    assert _post(client, _user_event("user.created", unique_clerk_id()), at=old).status_code == 400


def test_webhook_secret_not_configured_503(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "clerk_webhook_secret", "")
    assert _post(client, _user_event("user.created", unique_clerk_id())).status_code == 503


# --- User sync --------------------------------------------------------------


def test_user_created_provisions_user(client, db):
    cid = unique_clerk_id()
    resp = _post(client, _user_event("user.created", cid))
    assert resp.status_code == 200, resp.text
    user = db.query(User).filter_by(clerk_user_id=cid).one()
    assert user.email == "alice@example.com"
    assert user.name == "Alice Smith"


def test_primary_email_is_used_not_first(client, db):
    cid = unique_clerk_id()
    event = _user_event("user.created", cid, emails=("old@example.com", "primary@example.com"), primary_index=1)
    assert _post(client, event).status_code == 200
    assert db.query(User).filter_by(clerk_user_id=cid).one().email == "primary@example.com"


def test_user_without_email_stores_null(client, db):
    cid = unique_clerk_id()
    assert _post(client, _user_event("user.created", cid, emails=())).status_code == 200
    assert db.query(User).filter_by(clerk_user_id=cid).one().email is None


def test_duplicate_delivery_is_idempotent(client, db):
    cid = unique_clerk_id()
    payload = _user_event("user.created", cid)
    body, headers = _signed(payload, msg_id="msg_duplicate")
    for _ in range(3):
        assert client.post(URL, content=body, headers=headers).status_code == 200
    assert db.query(User).filter_by(clerk_user_id=cid).count() == 1


def test_created_then_updated_same_user(client, db):
    cid = unique_clerk_id()
    assert _post(client, _user_event("user.created", cid)).status_code == 200
    update = _user_event("user.updated", cid, emails=("new@example.com",), first="Alicia", last="Smith")
    assert _post(client, update).status_code == 200
    db.expire_all()
    users = db.query(User).filter_by(clerk_user_id=cid).all()
    assert len(users) == 1
    assert users[0].email == "new@example.com"
    assert users[0].name == "Alicia Smith"


def test_update_for_unknown_user_upserts(client, db):
    cid = unique_clerk_id()
    assert _post(client, _user_event("user.updated", cid)).status_code == 200
    assert db.query(User).filter_by(clerk_user_id=cid).count() == 1


def test_user_deleted_removes_user(client, db):
    cid = unique_clerk_id()
    assert _post(client, _user_event("user.created", cid)).status_code == 200
    deleted = {"type": "user.deleted", "data": {"id": cid, "object": "user", "deleted": True}}
    assert _post(client, deleted).status_code == 200
    assert db.query(User).filter_by(clerk_user_id=cid).count() == 0


def test_user_deleted_cascades_owned_rows(client, db):
    cid = unique_clerk_id()
    assert _post(client, _user_event("user.created", cid)).status_code == 200
    user_id = db.query(User).filter_by(clerk_user_id=cid).one().id
    db.add(Conversation(user_id=user_id, title="t"))
    db.commit()
    deleted = {"type": "user.deleted", "data": {"id": cid, "object": "user", "deleted": True}}
    resp = _post(client, deleted)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.query(User).filter_by(id=user_id).count() == 0
    assert db.query(Conversation).filter_by(user_id=user_id).count() == 0


def test_delete_unknown_user_is_noop(client):
    deleted = {"type": "user.deleted", "data": {"id": unique_clerk_id(), "deleted": True}}
    assert _post(client, deleted).status_code == 200


def test_unhandled_event_type_ignored(client, db):
    event = {"type": "session.created", "data": {"id": "sess_123", "user_id": unique_clerk_id()}}
    assert _post(client, event).status_code == 200
    assert db.query(User).count() == 0


def test_malformed_user_event_400(client):
    assert _post(client, {"type": "user.created", "data": {}}).status_code == 400
