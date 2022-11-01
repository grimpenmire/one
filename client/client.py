import os
import time
import json
import logging
import requests
from pyutils import config_logging, env, defenv


defenv('CLIENT_API_TOKEN', str, optional=False)
defenv('CLIENT_OUTPUT_DIR', str, default='/data')

logger = logging.getLogger(__name__)

cfd_config_template = '''
tunnel: {tunnel_id}
credentials-file: /etc/cloudflared/cfd-creds.json
no-autoupdate: true
ingress:
 - hostname: {hostname}
   service: http://ssv2ray
 - service: http_status:404
'''

api_hostname = 'https://grimpen.one/api/v1'

cf_config_file = f'{env.CLIENT_OUTPUT_DIR}/cfd-config.yml'
cf_creds_file = f'{env.CLIENT_OUTPUT_DIR}/cfd-creds.json'


def cleanup_old_files():
    for filename in [cf_config_file, cf_creds_file]:
        try:
            os.unlink(filename)
        except FileNotFoundError:
            pass


def main():
    config_logging()

    cleanup_old_files()

    token = env.CLIENT_API_TOKEN
    session = requests.Session()

    logger.info('Requesting tunnel...')
    while True:
        resp = session.get(
            f'{api_hostname}/connect/tunnel?token={token}')
        if 400 <= resp.status_code < 500:
            try:
                error = resp.json()
            except json.JSONDecodeError:
                error_desc = resp.content
            else:
                error_desc = error['description']
            logger.critical(
                f'Error {resp.status_code} from API server: '
                f'{error_desc}')
            exit(1)
        if 500 <= resp.status_code < 600:
            error = resp.json()
            error_desc = error['description']
            logger.critical(
                f'Error {resp.status_code} from API server: '
                f'{error_desc}')
            logger.info('Retrying in a moment...')
            time.sleep(5)
            continue

        resp = resp.json()

        if resp.get('status') == 'rejected':
            reason = resp.get('reject_reason')
            if reason:
                reason = f'Reason: {reason}'
            else:
                reason = ''
            logger.warning('Server rejected tunnel creation. {reason}')
            logger.info('Waiting for 1 minute before re-trying...')
            time.sleep(60)
            continue

        if resp.get('status') == 'ready':
            break

        logger.info('Tunnel is not created yet...')
        time.sleep(1)

    logger.info('Tunnel is ready.')

    cfd_creds = resp['cfd_creds']
    tunnel_id = cfd_creds['TunnelID']
    with open(f'{env.CLIENT_OUTPUT_DIR}/cfd-config.yml', 'w') as f:
        f.write(cfd_config_template.format(
            tunnel_id=tunnel_id,
            hostname=resp['hostname'],
        ))

    with open(f'{env.CLIENT_OUTPUT_DIR}/cfd-creds.json', 'w') as f:
        f.write(json.dumps(cfd_creds))

    logger.info('Starting heartbeat.')
    while True:
        time.sleep(15)
        logger.info('Sending heartbeat...')
        session.get(f'{api_hostname}/connect/tunnel?token={token}')



if __name__ == '__main__':
    main()
