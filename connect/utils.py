import os
import jwt
import jinja2
from uuid import uuid4
from base64 import b64encode, b32encode
from pyutils import env, defenv, get_redis

defenv('ONE_VERSION', str, optional=False)
defenv('CONNECT_SUBDOMAIN_SEED', int, optional=False)
defenv('CONNECT_SUBDOMAIN_PREFIX', str, default='t-')

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader('connect/templates/'))
docker_compose_template = jinja_env.get_template('docker-compose.yml')


def get_compose_file(redis, secret_key):
    tunnel_idx = redis.incr('connect:subdomain:idx')
    subdomain = get_subdomain(tunnel_idx)
    token = create_tunnel_token(secret_key, subdomain)
    version = env.ONE_VERSION
    ss_password = b64encode(os.urandom(9)).decode('ascii')
    ss_password += '#MahsaAmini'
    return docker_compose_template.render(
        token=token,
        one_version=version,
        ss_password=ss_password
    )


def create_tunnel_token(secret, tunnel_name):
    connector_id = str(uuid4())
    data = {
        'ver': 1,
        'cid': connector_id,
        'tname': tunnel_name,
    }
    token = jwt.encode(data, secret, algorithm='HS256')
    return token


def get_subdomain(idx):
    # Return a tunnel deterministically chosen sub-domain for the
    # given index.
    subdomain = lcg(idx)
    subdomain = subdomain.to_bytes(length=8, byteorder='big')
    subdomain = b32encode(subdomain)
    subdomain = subdomain.decode('ascii')
    subdomain = subdomain.strip('=')
    subdomain = subdomain.lower()
    subdomain = env.CONNECT_SUBDOMAIN_PREFIX + subdomain
    return subdomain


def lcg(n):
    # Generate a random number in range [0, 2**64). This function is a
    # linear Congruential Generator. When passed values from 0 to
    # 2**64-1 as n, it outputs a pseudo-random number in the 64-bit
    # space. `a` and `c` parameters are the ones chosen by Donald
    # Knuth's MMIX machine. The seed (x0) should be true 64-bit random
    # number, set in the environment.
    #
    # With a known seed value, this function generates a deterministic
    # sequence.
    #
    # The closed form of the LCG formula is taken from this article:
    # https://www.nayuki.io/page/fast-skipping-in-a-linear-congruential-generator
    #
    # Also see: https://en.wikipedia.org/wiki/Linear_congruential_generator

    a = 6364136223846793005
    c = 1442695040888963407
    m = 2 ** 64
    x0 = env.CONNECT_SUBDOMAIN_SEED
    return (((a**n * x0) % m) + ((a**n - 1) % ((a - 1) * m)) // (a - 1) * c) % m
