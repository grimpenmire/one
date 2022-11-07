from flask import (
    Blueprint, Flask, render_template, current_app as app, request,
    Response,
)
from pyutils import env, defenv, get_redis
from . import utils

defenv('WEBSITE_SECRET_KEY', str, optional=False)

bp = Blueprint('connect-website', __name__, url_prefix='/')


def create_app():
    app = Flask(__name__)
    app.secret_key = env.WEBSITE_SECRET_KEY
    app.register_blueprint(bp)

    app.redis = get_redis()

    return app


@bp.get('/')
def home_page():
    compose_code = utils.get_compose_file(app.redis, app.secret_key)
    return render_template(
        'index.html',
        docker_compose_code=compose_code,
    )


@bp.get('/docker-compose.yml')
def get_docker_compose_file():
    compose_file = utils.get_compose_file(app.redis, app.secret_key)
    download = request.args.get('dl', 'false')
    download = download.lower() in ['true', 't', 'yes', 'y']
    headers = {}
    if download:
        headers = {
            'Content-Disposition': 'attachment: filename=docker-compose.yml',
        }
    return Response(
        compose_file,
        mimetype='text/x-yaml',
        headers=headers,
    )
