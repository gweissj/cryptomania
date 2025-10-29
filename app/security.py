import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext

from .config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def compute_session_expiry() -> datetime:
    ttl_hours = max(settings.session_token_ttl_hours, 1)
    return datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
