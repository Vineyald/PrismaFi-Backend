"""Dramatiq broker.

Actor modules import `broker` from here so the broker is set before actors register:

    from app.core.broker import broker

    @dramatiq.actor(broker=broker)
    def some_job(...): ...

The worker process loads this module plus every actor module:

    dramatiq app.core.broker app.modules.<name>.tasks
"""

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import settings

broker = RedisBroker(url=settings.redis_url.unicode_string())  # type: ignore[no-untyped-call]
dramatiq.set_broker(broker)
