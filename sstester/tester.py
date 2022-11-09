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
from multiprocessing import Pool
from urllib.parse import urlparse, parse_qs
from pyutils import get_redis, config_logging

DEFAULT_SCRAPE_URL = 'https://raw.githubusercontent.com/WeAreMahsaAmini/FreeInternet/main/guides/shadowsocks-v2ray-tls/CONFIGS.md'
SCRAPE_URL = os.environ.get('SCRAPE_URL', DEFAULT_SCRAPE_URL)

DEFAULT_TEST_TIMEOUT = 60.0
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


def test_android_url(config, index):
    logger.info(f'Testing: {config["title"]}')

    # this method of port selection is not generally robust, but in a
    # container it's going to work fine.
    port = 1080 + index

    ss_local_args = [
        shutil.which('ss-local'),
        '-s', config['remote_addr'],
        '-p', str(config['remote_port']),
        '-l', str(port),
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
        return ('error', e, None)

    proxies = {
        'http': f'socks5h://localhost:{port}',
        'https': f'socks5h://localhost:{port}',
    }
    time_spent = 0
    last_exception = None
    start_time = time.monotonic()
    while True:
        if proc.poll() is not None:
            # ss-local terminated
            proc.kill()
            return ('not-working', 'terminated', None)
        try:
            resp = requests.get('https://google.com',
                                proxies=proxies,
                                timeout=TEST_TIMEOUT)
        except requests.ConnectionError as e:
            logger.debug('Connection error while testing; waiting...')
        except requests.Timeout as e:
            logger.debug('Request timeout while testing; waiting...')
        except requests.HTTPError as e:
            # http errors come from the web server; so the proxy is
            # working
            proc.kill()
            elapsed_time = time.monotonic() - start_time
            return ('working', 'http-error', elapsed_time)
        else:
            proc.kill()
            elapsed_time = time.monotonic() - start_time
            return ('working', 'success', elapsed_time)

        elapsed_time = time.monotonic() - start_time
        if elapsed_time > TEST_TIMEOUT:
            proc.kill()
            return ('not-working', 'timeout', elapsed_time)
        time.sleep(0.1)


def apply_test_android_url(args):
    return test_android_url(*args)


def main():
    config_logging()

    redis = get_redis()

    logger.info('Retrieving url list...')
    text = requests.get(SCRAPE_URL).text
    urls = re.findall(r'ss://.+$', text, re.MULTILINE)
    logger.info(f'Found {len(urls)} url(s).')

    results = []
    to_be_tested = {}
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
            results.append({
                'name': parsed_url.hostname,
                'config': {},
                'status': 'invalid',
                'error': str(e),
                'response_time': None,
            })
        else:
            to_be_tested[url] = config

    with Pool(20) as pool:
        logger.info(f'Testing {len(to_be_tested)} url(s)...')
        args = [
            (config, i)
            for i, config in enumerate(to_be_tested.values())
        ]
        for (url, config), (status, error, resp_time) in zip(
                to_be_tested.items(),
                pool.imap(apply_test_android_url, args)):
            results.append({
                'name': config['title'],
                'config': config,
                'status': status,
                'error': str(error),
                'response_time': resp_time,
            })
            if status == 'working':
                logger.info(f'{config["name"]}: working')
            else:
                logger.info(f'{config["name"]}: {status}   Error: {error}')

    def fix_resp_time(value):
        return value if value is not None else float('inf')
    results.sort(key=lambda r: fix_resp_time(r['response_time']))

    redis.set('vpn:status-list', json.dumps(results))
    logger.info('Done.')


if __name__ == '__main__':
    main()
