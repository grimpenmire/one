import os
import json
import jwt
from base64 import b64encode, b32encode
from uuid import uuid4
from flask import (
    Blueprint, Flask, jsonify, current_app as app, render_template,
    Response, request,
)
from pyutils import get_redis, env, defenv
from .tunnel import TunnelManager

bp = Blueprint('api', __name__, url_prefix='/')

defenv('API_SECRET_KEY', str, optional=False)
defenv('ONE_VERSION', str, optional=False)
defenv('CONNECT_SUBDOMAIN_SEED', int, optional=False)
defenv('CONNECT_SUBDOMAIN_PREFIX', str, default='t-')


def create_app():
    app = Flask(__name__)
    app.secret_key = env.API_SECRET_KEY
    app.register_blueprint(bp)
    app.register_error_handler(404, page_not_found)

    app.redis = get_redis()
    app.tunnel_manager = TunnelManager(app.redis)

    return app


def page_not_found(e):
    return jsonify({'description': 'Not Found'}), 404


@bp.get('/servers')
def get_servers():
    servers = app.redis.get('vpn:status-list')
    if servers is not None:
        servers = json.loads(servers)
    else:
        servers = []
    return jsonify({
        'value': servers,
    })


@bp.get('/connect/tunnel')
def get_tunnel():
    # This might not be strictly speaking RESTful, since the
    # get_tunnel function creates a 'pending' tunnel if one does not
    # exist. We could say that all tunnels actually exist all the
    # time, and the fact that we might create the key here is just an
    # implementation detail. The get_token function is idempotent, so
    # there will be no issues if this is called multiple times, even
    # in parallel.

    token = request.args.get('token')
    if token is None:
        token = request.headers.get('Authorization')
        if token and ' ' in token:
            kind, token = token.split(' ')
            if kind.lower() != 'bearer':
                token = None
    if token is None:
        return jsonify({'description': 'No token'}), 400

    try:
        token_data = jwt.decode(
            token, app.secret_key, algorithms=['HS256'])
    except jwt.InvalidTokenError:
        return jsonify({'description': 'Invalid token'}), 400

    if token_data['version'] != 1:
        return jsonify({'description': 'Unsupported token'}), 500

    tunnel = app.tunnel_manager.get_tunnel(token_data)
    return jsonify(tunnel)


@bp.get('/connect/token')
def get_token():
    tunnel_idx = app.redis.incr('connect:subdomain:idx')
    subdomain = get_subdomain(tunnel_idx)
    return jsonify({
        'token': create_tunnel_token(app.secret_key, subdomain)
    })


@bp.get('/connect/client')
def get_client():
    tunnel_idx = app.redis.incr('connect:subdomain:idx')
    subdomain = get_subdomain(tunnel_idx)
    token = create_tunnel_token(app.secret_key, subdomain)
    version = env.ONE_VERSION
    ss_password = b64encode(os.urandom(9)).decode('ascii')
    ss_password += '#MahsaAmini'
    yaml = render_template('client-docker-compose.yml',
                           token=token,
                           one_version=version,
                           ss_password=ss_password)
    return Response(
        yaml, mimetype='text/x-yaml',
        headers={
            'Content-Disposition': 'attachment; filename=docker-compose.yml',
        })


def create_tunnel_token(secret, tunnel_name):
    connector_id = str(uuid4())
    data = {
        'version': 1,
        'connector_id': connector_id,
        'tunnel_name': tunnel_name,
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
