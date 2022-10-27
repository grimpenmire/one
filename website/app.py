from flask import Blueprint, Flask, render_template, current_app as app
from pyutils import env
from pyutils.env import defenv

defenv('WEBSITE_SECRET_KEY', str, optional=False)

bp = Blueprint('website', __name__, url_prefix='/')


def create_app():
    app = Flask(__name__)
    app.secret_key = env.WEBSITE_SECRET_KEY
    app.register_blueprint(bp)

    return app


@bp.get('/')
def home_page():
    return render_template('index.html')
