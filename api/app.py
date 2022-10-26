import json
from flask import Blueprint, Flask, jsonify, current_app as app
from pyutils import get_redis
from pyutils import env
from pyutils.env import defenv

bp = Blueprint('api', __name__, url_prefix='/')

defenv('API_SECRET_KEY', str, optional=False)


def create_app():
    app = Flask(__name__)
    app.secret_key = env.API_SECRET_KEY
    app.register_blueprint(bp)
    app.register_error_handler(404, page_not_found)

    app.redis = get_redis()

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
