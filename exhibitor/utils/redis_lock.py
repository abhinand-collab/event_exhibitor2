# utils/redis_lock.py

import redis
from django.conf import settings
redis_client = redis.Redis.from_url(settings.CELERY_BROKER_URL)

def acquire_lock(lock_name, timeout=600):
    return redis_client.set(lock_name, "locked", nx=True, ex=timeout)

def release_lock(lock_name):
    redis_client.delete(lock_name)