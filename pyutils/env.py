import os
from dotenv import load_dotenv

load_dotenv()

_defs = {}


def defenv(name: str, var_type: type, default=None, optional=True):
    if name in _defs:
        # if the environment variable already exists, accept the
        # definition only if the new definition is the same as the old
        # one.
        definition = _defs[name]
        if definition['type'] != var_type or \
           definition['default'] != default or \
           definition['optional'] != optional:
            return
        raise ValueError('Conflicting environment variable definition.')

    _defs[name] = {
        'name': name,
        'type': var_type,
        'default': default,
        'optional': optional,
    }


def __getattr__(name):
    if name.startswith('_'):
        raise AttributeError

    if name not in _defs:
        raise ValueError(f'Unknown environment variable: {name}')

    definition = _defs[name]
    value = os.environ.get(name)
    if value is None:
        if definition['optional']:
            return definition['default']
        else:
            raise ValueError(f'Environment variable {name} not set')

    return definition['type'](value)
