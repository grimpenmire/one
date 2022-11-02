from multiprocessing import Process, Manager
from flask import Flask, jsonify, render_template
from pyutils import env


app = Flask(__name__)
manager = None
status = None


def launch_web_ui(host='0.0.0.0', port=80):
    global manager, status
    manager = Manager()
    status = manager.Namespace()
    status.android_link = None
    status.ios_link = None
    status.ready = False
    process = Process(target=app.run,
                      daemon=True,
                      kwargs={'port': port, 'host': host})
    process.start()


@app.get('/')
def get_index():
    return render_template(
        'index.html',
        status=status,
    )


@app.get('/status')
@app.post('/status')
def get_status():
    if status.ready:
        return jsonify({'status': 'ready'}), 200
    else:
        return jsonify({'status': 'not-ready'}), 412
