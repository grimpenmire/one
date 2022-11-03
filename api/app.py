import json
import jwt
import connect
from flask import (
    Blueprint, Flask, jsonify, current_app as app, render_template,
    Response, request,
)
from pyutils import get_redis, env, defenv
from .tunnel import TunnelManager

bp = Blueprint('api', __name__, url_prefix='/')

defenv('API_SECRET_KEY', str, optional=False)


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

    if token_data['ver'] != 1:
        return jsonify({'description': 'Unsupported token'}), 500

    tunnel = app.tunnel_manager.get_tunnel(token_data)
    return jsonify(tunnel)


@bp.get('/connect/token')
def get_token():
    tunnel_idx = app.redis.incr('connect:subdomain:idx')
    subdomain = connect.utils.get_subdomain(tunnel_idx)
    return jsonify({
        'token': connect.utils.create_tunnel_token(app.secret_key, subdomain)
    })
