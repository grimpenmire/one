import logging.config
from .env import defenv
from . import env

defenv('LOG_LEVEL', str, default='INFO')


def config_logging(log_level=None):
    if log_level is None:
        log_level = env.LOG_LEVEL
    log_level = log_level.upper()
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            }
        },
        'handlers': {
            'default': {
                'level': log_level,
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
            }
        },
        'loggers': {
            '': {
                'handlers': ['default'],
                'level': log_level,
                'propagate': True,
            },
        }
    })
