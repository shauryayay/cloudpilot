"""Celery worker configuration.

Celery handles the async provisioning pipeline. When the API receives a
provision request, it queues a Celery task instead of blocking — the API
returns a tracking ID immediately, and a background worker drives the
pipeline:

    render config → commit to Git → create resources → mark ready
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "cloudpilot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.autodiscover_tasks(["app"])
