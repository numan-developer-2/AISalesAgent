import hashlib
import hmac
import secrets
import time

from sqlalchemy import insert, select, delete
from workspace.database import sessions


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 600000
    ).hex()
    return f"pbkdf2${salt}${value}"


def check_password(password, encoded):
    try:
        scheme, salt, _ = encoded.split("$")
        return scheme == "pbkdf2" and hmac.compare_digest(
            hash_password(password, salt), encoded
        )
    except (ValueError, AttributeError):
        return False


def new_session(db, tenant, role, subject):
    token = secrets.token_urlsafe(40)
    with db.transaction() as c:
        c.execute(delete(sessions).where(sessions.c.expires < time.time()))
        c.execute(
            insert(sessions).values(
                hash=digest(token),
                tenant=tenant,
                role=role,
                subject=subject,
                expires=time.time() + (8 * 3600 if role == "admin" else 7 * 86400),
            )
        )
    return token


def get_session(db, token, role):
    if not token or len(token) > 100:
        return None
    with db.engine.connect() as c:
        row = c.execute(
            select(sessions).where(
                sessions.c.hash == digest(token),
                sessions.c.role == role,
                sessions.c.expires > time.time(),
            )
        ).first()
        return dict(row._mapping) if row else None


def revoke(db, token):
    with db.transaction() as c:
        c.execute(delete(sessions).where(sessions.c.hash == digest(token or "")))
