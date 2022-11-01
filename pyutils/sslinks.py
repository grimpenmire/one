import json
import urllib.parse
from base64 import b64encode


def get_ss_android_link(config):
    userinfo = f'{config["method"]}:{config["password"]}'
    userinfo = b64encode(userinfo.encode('ascii')).decode('ascii')
    userinfo = userinfo.rstrip('=')

    hostname = config['server']
    port = config['server_port']

    plugin = config['plugin']
    plugin_opts = urllib.parse.quote(';' + config['plugin_opts'])

    link = f'ss://{userinfo}@{hostname}:{port}?plugin={plugin}{plugin_opts}'
    return link


def get_ss_ios_link(config):
    hostname = config['server']
    userinfo = f'{config["method"]}:{config["password"]}'
    authority = f'{userinfo}@{hostname}:{config["server_port"]}'
    authority = b64encode(authority.encode('ascii'))
    authority = authority.decode('ascii').rstrip('=')

    plugin = config['plugin']
    plugin_opts = config['plugin_opts']
    plugin_path = '/'
    plugin_hostname = hostname
    for opt in plugin_opts.split(';'):
        if '=' in opt:
            k, v = opt.split('=')
            if k == 'host':
                plugin_hostname = v
            elif k == 'path':
                plugin_path = v
    plugin_opts = {
        'path': plugin_path,
        'host': plugin_hostname,
        'mux': True,
        'tfo': True,
        'mode': 'websocket',
        'tls': True,
    }
    plugin_opts = json.dumps(plugin_opts)
    plugin_opts = b64encode(plugin_opts.encode('ascii'))
    plugin_opts = plugin_opts.decode('ascii').rstrip('=')

    link = f'ss://{authority}?tfo=1&{plugin}={plugin_opts}'
    return link
