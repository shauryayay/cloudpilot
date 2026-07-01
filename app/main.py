"""cloudpilot — self-service database provisioning via GitOps.

    POST   /api/v1/clusters/provision       → queue a new cluster
    GET    /api/v1/clusters/{id}/status      → poll provisioning progress
    GET    /api/v1/clusters/{id}/credentials → retrieve derived passwords
    GET    /api/v1/clusters                  → list all clusters
    DELETE /api/v1/clusters/{id}             → mark a cluster as deleted
    GET    /health                           → liveness check
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.models import (
    ClusterInfo,
    ClusterRecord,
    CredentialEntry,
    CredentialResponse,
    ProvisionRequest,
    ProvisionResponse,
    ProvisionStatus,
    resolve_instance_type,
)
from app import store, secrets, tasks

app = FastAPI(
    title="cloudpilot",
    description=(
        "Self-service database provisioning API. Demonstrates GitOps-driven "
        "provisioning, deterministic secret derivation, and async task pipelines."
    ),
    version="0.1.0",
)


@app.post("/api/v1/clusters/provision", response_model=ProvisionResponse, status_code=202)
async def provision(req: ProvisionRequest):
    instance_type = resolve_instance_type(req.tier, req.engine)

    record = ClusterRecord(
        owner=req.owner,
        cluster_name=req.cluster_name,
        environment=req.environment,
        engine=req.engine,
        tier=req.tier,
        database=req.database,
        users=req.users,
        deletion_protection=req.deletion_protection,
        instance_type=instance_type,
    )
    await store.save(record)

    tasks.provision_cluster.delay(record.model_dump_json())

    return ProvisionResponse(
        tracking_id=record.tracking_id,
        status=ProvisionStatus.ACCEPTED,
        message=(
            f"Provisioning {req.engine.value} cluster '{req.cluster_name}' "
            f"for '{req.owner}' ({req.environment.value}). "
            f"Poll /api/v1/clusters/{record.tracking_id}/status for progress."
        ),
    )


@app.get("/api/v1/clusters/{tracking_id}/status", response_model=ClusterInfo)
async def get_status(tracking_id: str):
    record = await store.get(tracking_id)
    if not record:
        raise HTTPException(status_code=404, detail="Cluster not found")

    return ClusterInfo(
        tracking_id=record.tracking_id,
        status=record.status,
        owner=record.owner,
        cluster_name=record.cluster_name,
        engine=record.engine,
        environment=record.environment,
        created_at=record.created_at,
        updated_at=record.updated_at,
        instance_type=record.instance_type,
        host=record.host,
        port=record.port,
    )


@app.get("/api/v1/clusters/{tracking_id}/credentials", response_model=CredentialResponse)
async def get_credentials(tracking_id: str):
    record = await store.get(tracking_id)
    if not record:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if record.status != ProvisionStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=f"Cluster not ready — current status: {record.status.value}",
        )

    usernames = [u.name for u in record.users]
    creds = await secrets.derive_credentials(
        owner=record.owner,
        cluster=record.cluster_name,
        env=record.environment.value,
        usernames=usernames,
    )

    return CredentialResponse(
        tracking_id=record.tracking_id,
        cluster_name=record.cluster_name,
        credentials={
            username: CredentialEntry(username=username, password=password)
            for username, password in creds.items()
        },
    )


@app.get("/api/v1/clusters", response_model=list[ClusterInfo])
async def list_clusters():
    records = await store.list_all()
    return [
        ClusterInfo(
            tracking_id=r.tracking_id,
            status=r.status,
            owner=r.owner,
            cluster_name=r.cluster_name,
            engine=r.engine,
            environment=r.environment,
            created_at=r.created_at,
            updated_at=r.updated_at,
            instance_type=r.instance_type,
            host=r.host,
            port=r.port,
        )
        for r in records
    ]


@app.delete("/api/v1/clusters/{tracking_id}")
async def delete_cluster(tracking_id: str):
    record = await store.get(tracking_id)
    if not record:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if record.deletion_protection:
        raise HTTPException(
            status_code=403,
            detail="deletion_protection is enabled. Disable it first.",
        )

    await store.update_status(tracking_id, ProvisionStatus.FAILED, error="Deleted by user")
    return {"tracking_id": tracking_id, "status": "deleted"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "cloudpilot"}
