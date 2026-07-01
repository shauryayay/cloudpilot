"""Celery tasks that drive the provisioning pipeline.

Stages:
    1. RENDERING  — render Chart.yaml + values.yaml from the request
    2. COMMITTED  — push the files to the GitOps repo
    3. CREATING   — simulate cloud resource creation
    4. READY      — cluster is live, host + port available

Each stage updates the cluster record in Redis so the /status endpoint
reflects real-time progress.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time

from app.worker import celery_app
from app.config import settings
from app.models import ClusterRecord, ProvisionStatus
from app import store, generator, gitops


def _run_async(coro):
    """Run an async function from sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=5)
def provision_cluster(self, record_json: str) -> dict:
    record = ClusterRecord.model_validate_json(record_json)
    tid = record.tracking_id

    try:
        _run_async(store.update_status(tid, ProvisionStatus.RENDERING))
        time.sleep(1)

        chart_yaml = generator.generate_chart_yaml(record)
        values_yaml = generator.generate_values_yaml(record)

        _run_async(store.update_status(tid, ProvisionStatus.COMMITTED))
        commit_sha = gitops.commit_provision(
            owner=record.owner,
            cluster_name=record.cluster_name,
            environment=record.environment.value,
            chart_yaml=chart_yaml,
            values_yaml=values_yaml,
        )
        _run_async(
            store.update_status(tid, ProvisionStatus.COMMITTED, commit_sha=commit_sha)
        )

        _run_async(store.update_status(tid, ProvisionStatus.CREATING))
        provision_time = random.randint(
            settings.provision_delay_min, settings.provision_delay_max
        )
        time.sleep(provision_time)

        host_hash = hashlib.md5(
            f"{record.owner}-{record.cluster_name}".encode()
        ).hexdigest()[:8]
        host = (
            f"{record.cluster_name}-{host_hash}"
            f".{record.environment.value}.cloudpilot.local"
        )
        port = generator.get_port(record.engine)

        _run_async(
            store.update_status(
                tid,
                ProvisionStatus.READY,
                host=host,
                port=port,
            )
        )

        return {"tracking_id": tid, "status": "ready", "host": host}

    except Exception as exc:
        _run_async(
            store.update_status(tid, ProvisionStatus.FAILED, error=str(exc))
        )
        raise self.retry(exc=exc)
