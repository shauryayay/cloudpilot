"""Thin async wrapper around Redis for cluster record persistence.

Each ClusterRecord is stored as a JSON blob keyed by tracking_id.
A sorted set (by created_at) supports listing. Redis serves as the
fast state store for tracking provisioning progress, separate from
the Git-based source of truth.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.config import settings
from app.models import ClusterRecord, ProvisionStatus

PREFIX = "cloudpilot:cluster:"
INDEX_KEY = "cloudpilot:clusters"


def _key(tracking_id: str) -> str:
    return f"{PREFIX}{tracking_id}"


async def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def save(record: ClusterRecord) -> None:
    r = await _redis()
    try:
        await r.set(_key(record.tracking_id), record.model_dump_json())
        await r.zadd(INDEX_KEY, {record.tracking_id: datetime.now(timezone.utc).timestamp()})
    finally:
        await r.aclose()


async def get(tracking_id: str) -> ClusterRecord | None:
    r = await _redis()
    try:
        raw = await r.get(_key(tracking_id))
        if not raw:
            return None
        return ClusterRecord.model_validate_json(raw)
    finally:
        await r.aclose()


async def update_status(
    tracking_id: str,
    status: ProvisionStatus,
    *,
    commit_sha: str | None = None,
    host: str | None = None,
    port: int | None = None,
    error: str | None = None,
) -> None:
    record = await get(tracking_id)
    if not record:
        return
    record.status = status
    record.updated_at = datetime.now(timezone.utc).isoformat()
    if commit_sha:
        record.commit_sha = commit_sha
    if host:
        record.host = host
    if port:
        record.port = port
    if error:
        record.error = error
    await save(record)


async def list_all() -> list[ClusterRecord]:
    r = await _redis()
    try:
        ids = await r.zrevrange(INDEX_KEY, 0, 99)
        records = []
        for tid in ids:
            rec = await get(tid)
            if rec:
                records.append(rec)
        return records
    finally:
        await r.aclose()
