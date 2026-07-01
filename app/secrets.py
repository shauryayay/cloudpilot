"""Deterministic secret derivation.

Instead of generating random passwords and storing them somewhere (Git, Vault, etc.),
we derive passwords *deterministically* from a seed + a structured salt.

  password = sha256(seed + "|" + salt)[:32]

The seed is a random value created once and stored as a secret (here, in Redis).
The salt encodes identity: owner, cluster, environment, user, version.

This means:
  - The same inputs always produce the same password  → idempotent re-runs are safe
  - No password is ever written to Git                → no secrets in source control
  - Rotating a password = bumping the version in the salt → new derivation, old seed
"""

import hashlib
import base64
import secrets as stdlib_secrets

import redis.asyncio as aioredis

from app.config import settings

SEED_KEY = "cloudpilot:seed"


async def _get_or_create_seed(r: aioredis.Redis) -> str:
    """Fetch the global seed from Redis, or create one if it doesn't exist."""
    seed = await r.get(SEED_KEY)
    if seed:
        return seed.decode()
    new_seed = stdlib_secrets.token_urlsafe(54)
    await r.set(SEED_KEY, new_seed, nx=True)
    return (await r.get(SEED_KEY)).decode()


def _derive_password(seed: str, salt: str) -> str:
    """SHA-256 derivation: hash the seed+salt, base64-encode, strip
    non-alphanumeric chars, and truncate to 32 characters."""
    raw = hashlib.sha256(f"{seed}|{salt}".encode()).digest()
    b64 = base64.b64encode(raw).decode()
    cleaned = b64.translate(str.maketrans("", "", "/+="))
    return cleaned[:32]


async def derive_credentials(
    owner: str,
    cluster: str,
    env: str,
    usernames: list[str],
    version: str = "v1",
) -> dict[str, str]:
    """Derive a password for each database user.

    Returns {username: derived_password}.

    The salt structure:
        cred|{owner}|{cluster}|{env}|{username}|{version}
    ensures each user in each environment gets a unique, reproducible password.
    """
    r = aioredis.from_url(settings.redis_url)
    try:
        seed = await _get_or_create_seed(r)
    finally:
        await r.aclose()

    creds: dict[str, str] = {}
    for username in usernames:
        salt = f"cred|{owner}|{cluster}|{env}|{username}|{version}"
        creds[username] = _derive_password(seed, salt)
    return creds
