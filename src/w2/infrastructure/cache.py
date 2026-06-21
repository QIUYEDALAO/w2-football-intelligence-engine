from __future__ import annotations

from redis import Redis
from redis.exceptions import RedisError

from w2.config import Settings, get_settings


def create_redis(settings: Settings | None = None) -> Redis | None:
    resolved = settings or get_settings()
    if resolved.redis_url is None:
        return None
    return Redis.from_url(resolved.redis_url.get_secret_value(), socket_connect_timeout=1)


def redis_status(settings: Settings | None = None) -> str:
    client = create_redis(settings)
    if client is None:
        return "disabled"
    try:
        return "ok" if client.ping() else "unavailable"
    except RedisError:
        return "unavailable"

