import sys
import time
import logging
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from .env import defenv
from . import env

logger = logging.getLogger(__name__)

defenv('REDIS_MAIN', str, default='redis')
defenv('REDIS_MAX_RETRIES', int, default=30)


def get_redis(port=6379, decode_responses=False):
    redis_host = env.REDIS_MAIN
    redis = Redis(host=redis_host, port=port,
                  decode_responses=decode_responses)
    make_sure_redis_is_up(redis, redis_host, port)
    return redis


def make_sure_redis_is_up(redis, redis_host, redis_port):
    max_retries = env.REDIS_MAX_RETRIES
    retries = 0

    while True:
        try:
            # We need to attempt sending a command to redis to see if
            # it's actually available.
            redis.get('_dummy_key_readiness_check')
        except RedisConnectionError:
            logger.warning('Redis not up yet at %s:%d . Re-trying...',
                           redis_host, redis_port)
            time.sleep(1.0)
            retries += 1

            if retries >= max_retries:
                logger.error("Maximum retries (%s) reached, "
                             "attempting to connect to redis. Aborting.", max_retries)
                sys.exit(1)
        else:
            return
