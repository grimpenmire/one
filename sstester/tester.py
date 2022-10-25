#!/usr/bin/env python3

import os
import re
import time
import json
import shutil
import base64
import logging
import subprocess
import requests
from urllib.parse import urlparse, parse_qs
from pyutils import get_redis, config_logging

DEFAULT_SCRAPE_URL = 'https://raw.githubusercontent.com/WeAreMahsaAmini/FreeInternet/main/guides/shadowsocks-v2ray-tls/CONFIGS.md'
SCRAPE_URL = os.environ.get('SCRAPE_URL', DEFAULT_SCRAPE_URL)

DEFAULT_TEST_TIMEOUT = 3.0
TEST_TIMEOUT = int(os.environ.get('TEST_TIMEOUT', DEFAULT_TEST_TIMEOUT))

logger = logging.getLogger(__name__)


class SsUrlParseError(Exception):
    pass


def detect_url_type(parsed_url):
    if parsed_url.username is not None:
        return 'android'
    else:
        return 'other'


def get_config_from_android_url(parsed_url):
    qs = parse_qs(parsed_url.query)
    if 'plugin' not in qs:
        raise SsUrlParseError('No plugin value in query string')

    plugin_config = qs['plugin'][0]

    try:
        plugin, plugin_opts = plugin_config.split(';', 1)
    except (TypeError, ValueError):
        raise SsUrlParseError(
            f'Invalid plugin options: {plugin_config}')

    if plugin != 'v2ray-plugin':
        raise SsUrlParseError(f'Unknown plugin: {plugin}')

    # The input url might not have padding. In order to prevent parse
    # errors, we add the maximum number of paddings (2) to the URL,
    # which will be safely ignored if not needed.
    params = base64.urlsafe_b64decode(parsed_url.username + '==').decode('utf-8')

    method, password = params.split(':', 1)

    if parsed_url.port is None:
        raise SsUrlParseError(f'No remote port in url')

    name = parsed_url.fragment
    if name:
        title = f'{parsed_url.hostname} ({name})'
    else:
        name = parsed_url.hostname
        title = name

    return {
        'name': name,
        'title': title,
        'remote_addr': parsed_url.hostname,
        'remote_port': parsed_url.port,
        'method': method,
        'password': password,
        'plugin': plugin,
        'plugin_opts': plugin_opts,
    }


def test_android_url(config):
    ss_local_args = [
        shutil.which('ss-local'),
        '-s', config['remote_addr'],
        '-p', str(config['remote_port']),
        '-l', '1080',
        '-k', config['password'],
        '-m', config['method'],
        '--plugin', config['plugin'],
        '--plugin-opts', config['plugin_opts'],
    ]

    logger.debug(f'Executing: {" ".join(ss_local_args)}')
    try:
        proc = subprocess.Popen(
            ss_local_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.error(f'Error executing ss-local: {e}')
        return ('error', e)

    proxies = {
        'http': 'socks5h://localhost:1080',
        'https': 'socks5h://localhost:1080',
    }
    time_spent = 0
    last_exception = None
    start_time = time.monotonic()
    while True:
        if proc.poll() is not None:
            # ss-local terminated
            proc.kill()
            return ('not-working', 'terminated')
        try:
            resp = requests.get('https://google.com', proxies=proxies)
        except requests.ConnectionError as e:
            logger.debug('Connection error while testing; waiting...')
        except requests.Timeout as e:
            logger.debug('Request timeout while testing; waiting...')
        except requests.HTTPError as e:
            # http errors come from the web server; so the proxy is
            # working
            proc.kill()
            return ('working', 'http-error')
        else:
            proc.kill()
            return ('working', 'success')

        if time.monotonic() - start_time > TEST_TIMEOUT:
            proc.kill()
            return ('not-working', 'timeout')
        time.sleep(0.1)


def main():
    config_logging()

    redis = get_redis()

    logger.info('Retrieving url list...')
    text = requests.get(SCRAPE_URL).text
    urls = re.findall(r'ss://.+$', text, re.MULTILINE)
    logger.info(f'Found {len(urls)} url(s).')

    results = []
    for url in urls:
        parsed_url = urlparse(url)
        url_type = detect_url_type(parsed_url)
        if url_type != 'android':
            continue

        try:
            config = get_config_from_android_url(parsed_url)
        except SsUrlParseError as e:
            logger.info(f'Invalid URL: {url}')
            logger.debug(f'Error: {e}')
            status = 'invalid'
            error = e
        else:
            logger.info(f'Testing: {config["title"]}')
            status, error = test_android_url(config)

        if status == 'working':
            logger.info('Status: working')
        else:
            logger.info(f'Status: {status}   Error: {error}')
        results.append({
            'name': config['title'],
            'config': config,
            'status': status,
            'error': str(error),
        })

    redis.set('vpn:status-list', json.dumps(results))
    logger.info('Done.')


if __name__ == '__main__':
    main()
