from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "nexusmind",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.crawl",
        "app.workers.tasks.embed",
        "app.workers.tasks.dataset",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.crawl.*": {"queue": "crawl"},
        "app.workers.tasks.embed.*": {"queue": "embed"},
        "app.workers.tasks.dataset.*": {"queue": "dataset"},
    },
)
