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

# Register task modules explicitly.
# Note: autodiscover_tasks() assumes a tasks.py convention; conf.include is
# the correct mechanism for non-standard module names.
celery_app.conf.include = ["workers.simulation", "workers.build_actions"]

# Beat schedule — tick all cities every 10 seconds.
# "queue" must be explicit; task_default_queue is high_priority.
celery_app.conf.beat_schedule = {
    "tick-all-cities": {
        "task": "workers.simulation.tick_all_cities",
        "schedule": 10.0,
        "queue": "simulation",
    }
}
