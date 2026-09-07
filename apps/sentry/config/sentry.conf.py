from __future__ import annotations

import os

from sentry.conf.server import *  # noqa: F403,F401


env = os.environ.get

DATABASES = {
    "default": {
        "ENGINE": "sentry.db.postgres",
        "NAME": env("SENTRY_DB_NAME", "sentry"),
        "USER": env("SENTRY_DB_USER", "sentry"),
        "PASSWORD": env("SENTRY_DB_PASSWORD", ""),
        "HOST": env("SENTRY_POSTGRES_HOST", "172.17.0.24"),
        "PORT": env("SENTRY_POSTGRES_PORT", "5432"),
    }
}

SENTRY_SINGLE_ORGANIZATION = True
SENTRY_SELF_HOSTED_ERRORS_ONLY = True
SENTRY_USE_RELAY = True

SENTRY_OPTIONS["system.event-retention-days"] = int(env("SENTRY_EVENT_RETENTION_DAYS", "90"))
_secret_key = env("SENTRY_SECRET_KEY") or env("SENTRY_SYSTEM_SECRET_KEY")
if not _secret_key:
    raise RuntimeError("SENTRY_SECRET_KEY or SENTRY_SYSTEM_SECRET_KEY must be set")
SENTRY_OPTIONS["system.secret-key"] = _secret_key

_redis_host = env("SENTRY_REDIS_HOST", "redis")
_redis_port = env("SENTRY_REDIS_PORT", "6379")
_redis_password = env("SENTRY_REDIS_PASSWORD", "")
_redis_db = env("SENTRY_REDIS_DB", "3")

SENTRY_OPTIONS["redis.clusters"] = {
    "default": {
        "hosts": {
            0: {
                "host": _redis_host,
                "port": _redis_port,
                "password": _redis_password,
                "db": _redis_db,
            }
        }
    }
}

CACHES = {
    "default": {
        "BACKEND": "sentry.cache.backends.reconnectingmemcache.ReconnectingMemcache",
        "LOCATION": [
            f"{env('SENTRY_MEMCACHED_HOST', 'memcached')}:{env('SENTRY_MEMCACHED_PORT', '11211')}"
        ],
        "TIMEOUT": 3600,
        "OPTIONS": {"ignore_exc": True, "reconnect_age": 300},
    }
}

SENTRY_CACHE = "sentry.cache.redis.RedisCache"
SENTRY_RATELIMITER = "sentry.ratelimits.redis.RedisRateLimiter"
SENTRY_BUFFER = "sentry.buffer.redis.RedisBuffer"
SENTRY_QUOTAS = "sentry.quotas.redis.RedisQuota"
SENTRY_TSDB = "sentry.tsdb.redissnuba.RedisSnubaTSDB"
SENTRY_DIGESTS = "sentry.digests.backends.redis.RedisBackend"

DEFAULT_KAFKA_OPTIONS = {
    "bootstrap.servers": env("SENTRY_KAFKA_BROKERS", "kafka:9092"),
    "message.max.bytes": 50000000,
    "socket.timeout.ms": 1000,
}
KAFKA_CLUSTERS["default"] = DEFAULT_KAFKA_OPTIONS
SENTRY_EVENTSTREAM = "sentry.eventstream.kafka.KafkaEventStream"
SENTRY_EVENTSTREAM_OPTIONS = {"producer_configuration": DEFAULT_KAFKA_OPTIONS}

SENTRY_SEARCH = "sentry.search.snuba.EventsDatasetSnubaSearchBackend"
SENTRY_SEARCH_OPTIONS = {}
SENTRY_TAGSTORE = "sentry.tagstore.snuba.SnubaTagStorage"
SENTRY_TAGSTORE_OPTIONS = {}

SENTRY_NODESTORE = "sentry.services.nodestore.django.DjangoNodeStorage"
SENTRY_NODESTORE_OPTIONS = {}

SENTRY_WEB_HOST = "0.0.0.0"
SENTRY_WEB_PORT = 9000
SENTRY_WEB_OPTIONS = {
    "http": f"{SENTRY_WEB_HOST}:{SENTRY_WEB_PORT}",
    "protocol": "uwsgi",
    "uwsgi-socket": None,
    "so-keepalive": True,
    "http-keepalive": 15,
    "http-chunked-input": True,
    "workers": 2,
    "threads": 4,
    "memory-report": False,
    "buffer-size": 32768,
    "limit-post": 209715200,
    "disable-logging": True,
    "reload-on-rss": 600,
    "ignore-sigpipe": True,
    "ignore-write-errors": True,
    "disable-write-exception": True,
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
CSRF_TRUSTED_ORIGINS = ["https://sentry.albandrieu.com"]

SENTRY_OPTIONS["mail.backend"] = "dummy"
SENTRY_OPTIONS["mail.from"] = "sentry@localhost"
