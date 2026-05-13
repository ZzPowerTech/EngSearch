"""Celery application configuration."""
import os

from celery import Celery

app = Celery(
    "engsearch",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        "tasks.email_task",
        "tasks.followup_task",
    ],
)

app.conf.update(
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,          # re-queue if worker crashes mid-task
    worker_prefetch_multiplier=1, # fair scheduling — important for long AI tasks
)
