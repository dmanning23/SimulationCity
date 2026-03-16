from celery import Celery

from app.config import settings

celery_app = Celery(
    "simulationcity",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_queues={
        "high_priority": {
            "exchange": "high_priority",
            "routing_key": "high_priority",
        },
        "simulation": {
            "exchange": "simulation",
            "routing_key": "simulation",
        },
    },
    task_default_queue="high_priority",
)

# Future task modules are registered here as the project grows:
# celery_app.autodiscover_tasks(["workers.simulation", "workers.build_actions"])
