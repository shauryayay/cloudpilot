from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Engine(str, Enum):
    POSTGRES = "postgres"
    MYSQL = "mysql"
    MONGO = "mongo"
    REDIS = "redis"


class Environment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class Tier(str, Enum):
    STARTER = "starter"
    STANDARD = "standard"
    PERFORMANCE = "performance"


_TIER_MAP: dict[Tier, dict[Engine, str]] = {
    Tier.STARTER: {
        Engine.POSTGRES: "db.t4g.medium",
        Engine.MYSQL: "db.t4g.medium",
        Engine.MONGO: "db.t4g.medium",
        Engine.REDIS: "cache.t4g.micro",
    },
    Tier.STANDARD: {
        Engine.POSTGRES: "db.r6g.large",
        Engine.MYSQL: "db.r6g.large",
        Engine.MONGO: "db.r6g.large",
        Engine.REDIS: "cache.r7g.large",
    },
    Tier.PERFORMANCE: {
        Engine.POSTGRES: "db.r6g.2xlarge",
        Engine.MYSQL: "db.r6g.2xlarge",
        Engine.MONGO: "db.r6g.2xlarge",
        Engine.REDIS: "cache.r7g.2xlarge",
    },
}


def resolve_instance_type(tier: Tier, engine: Engine) -> str:
    return _TIER_MAP[tier][engine]


class DBUser(BaseModel):
    name: str = Field(min_length=1, max_length=63, pattern=r"^[a-z_][a-z0-9_]*$")
    privileges: str = Field(default="readWrite", description="Database privilege set")


class ProvisionRequest(BaseModel):
    """Provision a new managed database cluster."""

    owner: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9-]+$")
    cluster_name: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9-]+$")
    environment: Environment
    engine: Engine
    tier: Tier = Tier.STARTER
    database: str = Field(
        default="appdb", min_length=1, max_length=63, pattern=r"^[a-z_][a-z0-9_]*$"
    )
    users: list[DBUser] = Field(default_factory=lambda: [DBUser(name="appuser")])
    deletion_protection: bool = False

    @field_validator("deletion_protection", mode="after")
    @classmethod
    def prod_must_protect(cls, v: bool, info) -> bool:
        env = info.data.get("environment")
        if env == Environment.PROD and not v:
            raise ValueError("deletion_protection must be true for prod environment")
        return v


class ProvisionStatus(str, Enum):
    ACCEPTED = "accepted"
    RENDERING = "rendering"
    COMMITTED = "committed"
    CREATING = "creating"
    READY = "ready"
    FAILED = "failed"


class ProvisionResponse(BaseModel):
    tracking_id: str
    status: ProvisionStatus
    message: str


class ClusterInfo(BaseModel):
    tracking_id: str
    status: ProvisionStatus
    owner: str
    cluster_name: str
    engine: Engine
    environment: Environment
    created_at: str
    updated_at: str
    instance_type: str
    host: str | None = None
    port: int | None = None


class CredentialResponse(BaseModel):
    tracking_id: str
    cluster_name: str
    credentials: dict[str, CredentialEntry]


class CredentialEntry(BaseModel):
    username: str
    password: str
    method: str = "sha256(seed + salt)"


class ClusterRecord(BaseModel):
    """State persisted in Redis for each provisioned cluster."""

    tracking_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    owner: str
    cluster_name: str
    environment: Environment
    engine: Engine
    tier: Tier
    database: str
    users: list[DBUser]
    deletion_protection: bool
    instance_type: str
    status: ProvisionStatus = ProvisionStatus.ACCEPTED
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    host: str | None = None
    port: int | None = None
    commit_sha: str | None = None
    error: str | None = None
