import re
import secrets
import string
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from anyio import to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApiKey, User

_hasher = PasswordHasher()
_ALPHABET = string.ascii_lowercase + string.digits
_RAW_RE = re.compile(r"^ih_([a-z0-9]{8})_([A-Za-z0-9_-]{32})$")
LAST_USED_INTERVAL = timedelta(minutes=1)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


async def create_api_key(
    session: AsyncSession,
    user: User,
    name: str,
    scopes: Sequence[str],
    expires_at: datetime | None,
) -> tuple[ApiKey, str]:
    secret = secrets.token_urlsafe(24)[:32]  # 32 urlsafe characters
    while True:
        prefix = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        exists = await session.execute(select(ApiKey.id).where(ApiKey.prefix == prefix))
        if exists.first() is None:
            break
    digest = await to_thread.run_sync(_hasher.hash, secret)
    key = ApiKey(
        user_id=user.id,
        name=name,
        prefix=prefix,
        hash=digest,
        scopes=list(scopes),
        expires_at=_naive(expires_at) if expires_at else None,
    )
    session.add(key)
    await session.flush()
    return key, f"ih_{prefix}_{secret}"


def _verify(digest: str, secret: str) -> bool:
    try:
        return _hasher.verify(digest, secret)
    except (VerificationError, InvalidHashError):
        return False


async def verify_api_key(session: AsyncSession, raw: str) -> ApiKey | None:
    m = _RAW_RE.match(raw)
    if not m:
        return None
    prefix, secret = m.groups()
    key = (
        await session.execute(select(ApiKey).where(ApiKey.prefix == prefix))
    ).scalar_one_or_none()
    if key is None or key.revoked:
        return None
    now = _now()
    if key.expires_at is not None and _naive(key.expires_at) <= now:
        return None
    if not await to_thread.run_sync(_verify, key.hash, secret):
        return None
    if key.last_used_at is None or now - key.last_used_at >= LAST_USED_INTERVAL:
        key.last_used_at = now
        await session.flush()
    return key
