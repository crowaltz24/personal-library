import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

SECRET = os.getenv("AUTH_SECRET", "development-only-change-me")
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt_text, digest_text = encoded.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(digest_text)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return hmac.compare_digest(actual, expected)


def _encode(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return f"{body.decode()}.{encoded_signature.decode()}"


def _decode(token: str) -> dict:
    try:
        body_text, signature_text = token.split(".", 1)
        body = body_text.encode()
        expected = hmac.new(SECRET.encode(), body, hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(signature_text + "===")
        if not hmac.compare_digest(actual, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(body_text + "===").decode())
        if payload["exp"] < time.time():
            raise ValueError
        return payload
    except (KeyError, ValueError, TypeError, binascii.Error, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def create_access_token(user_id: int) -> str:
    return _encode({"sub": user_id, "exp": time.time() + 60 * 60 * 24 * 30})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required")
    payload = _decode(credentials.credentials)
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user