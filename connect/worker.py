import os
import json
import time
import signal
import logging
import requests
from functools import wraps
from base64 import b64encode
from CloudFlare import CloudFlare
from CloudFlare.exceptions import CloudFlareAPIError
from pyutils import env, defenv, get_redis, config_logging
from api.tunnel import TunnelManager


defenv('CLOUDFLARE_ACCOUNT_ID', str, optional=False)
defenv('CLOUDFLARE_ZONE_ID', str, optional=False)
defenv('MAX_CF_TUNNELS', int, default=500)
defenv('CONNECT_DOMAIN', str, optional=False)
defenv('CONNECT_SUBDOMAIN_PREFIX', str, default='t-')

keep_running = True
logger = logging.getLogger()

account_id = env.CLOUDFLARE_ACCOUNT_ID
zone_id = env.CLOUDFLARE_ZONE_ID
max_tunnels = env.MAX_CF_TUNNELS
domain = env.CONNECT_DOMAIN

cf = None
tunnel_mng = None

def signal_handler(signum, _):
    global keep_running
    keep_running = False

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)


def create_tunnel(connector_id, tunnel_name):
    logger.info('Creating Cloudflare tunnel...')
    tunnel_secret = b64encode(os.urandom(32)).decode('ascii')
    tunnel = cf.accounts.cfd_tunnel.post(
        account_id,
        data={'name': tunnel_name, 'tunnel_secret': tunnel_secret}
    )

    tunnel_id = tunnel['id']
    logger.info(
        f'Created Cloudflare tunnel: {tunnel_name} ({tunnel_id})')

    logger.info('Configuring Cloudflare tunnel...')
    hostname = f'{tunnel_name}.{domain}'
    path = 'graphql'  # just a random end-point for v2ray
    cf.accounts.cfd_tunnel.configurations.put(
        account_id, tunnel_id,
        data={
            'config': {
                'ingress': [
                    {
                        'hostname': hostname,
                        'path': path,
                        'service': 'http://ssv2ray',
                    },
                    {
                        'service': 'http_status:404'
                    },
                ],
            },
        },
    )
    logger.info('Cloudflare tunnel configured.')

    logger.info('Adding DNS record...')
    cf.zones.dns_records.post(
        zone_id,
        data={
            'type': 'CNAME',
            'name': hostname,
            'content': f'{tunnel_id}.cfargotunnel.com',
            'ttl': 1,  # 1 = automatic
            'proxied': True,
        }
    )
    logger.info('DNS record created.')

    logger.info('Tunnel created.')

    cfd_creds = {
        'AccountTag': account_id,
        'TunnelID': tunnel_id,
        'TunnelSecret': tunnel_secret,
    }
    tunnel_mng.write_tunnel(
        connector_id,
        tunnel_name,
        hostname=hostname,
        path=path,
        cfd_creds=cfd_creds,
        status='ready',
    )


def retry(f):
    retries = 5
    wait_time = 1

    @wraps(f)
    def wrapper(*args, **kwargs):
        while True:
            try:
                return f(*args, **kwargs)
            except (requests.RequestException, CloudFlareAPIError) as e:
                logger.warning(f'Request error while performing cf API call: {e}')
                if retries == 0:
                    logger.error('Not retrying anymore.')
                    raise

            logger.info(f'Retrying after {wait_time} second(s)...')
            time.sleep(wait_time)
            wait_time *= 2

    return wrapper


@retry
def get_all_cf_tunnels():
    cf_tunnels = cf.accounts.cfd_tunnel.get(
        account_id, params={'is_deleted': 'false'},
    )
    cf_tunnels = [
        t for t in cf_tunnels
        if t['name'].startswith(env.CONNECT_SUBDOMAIN_PREFIX)
    ]
    return cf_tunnels


@retry
def delete_cf_tunnel(tunnel_id):
    cf.accounts.cfd_tunnel.delete(account_id, tunnel_id)


@retry
def get_all_dns_records(zone_id):
    return cf.zones.dns_records.get(zone_id)


@retry
def delete_dns_record(zone_id, dns_record_id):
    cf.zones.dns_records.delete(zone_id, dns_record_id)


def main():
    global cf, tunnel_mng

    config_logging()
    redis = get_redis(decode_responses=True)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    cf = CloudFlare()
    tunnel_mng = TunnelManager(redis)

    logger.info('Started.')

    while keep_running:
        reject = False
        reject_reason = None
        cf_tunnels = get_all_cf_tunnels()
        if len(cf_tunnels) >= max_tunnels:
            reject = True
            reject_reason = 'No free tunnels available.'
            logger.info(
                'Hit max number of tunnels. Will reject requests.')
        else:
            logger.debug(
                f'There are {len(cf_tunnels)} existing cf tunnels '
                f'(max={max_tunnels})')

        for key in redis.scan_iter('tunnel:*'):
            tunnel = redis.get(key)
            tunnel = json.loads(tunnel)
            if tunnel['hostname'] is not None:
                continue

            _, connector_id = key.split(':', maxsplit=1)

            if reject:
                tunnel_mng.write_tunnel(
                    connector_id, tunnel['tunnel_name'],
                    status='rejected',
                    reject_reason=reject_reason)
                continue

            logger.info(
                f'Creating tunnel for connector: {connector_id}...')

            create_tunnel(connector_id, tunnel['tunnel_name'])

        active_cf_tunnel_ids = []
        for key in redis.scan_iter('tunnel:*'):
            _, connector_id = key.split(':', maxsplit=1)
            tunnel = redis.get(f'tunnel:{connector_id}')
            tunnel = json.loads(tunnel)
            cf_tunnel_creds = tunnel.get('cfd_creds', {})
            cf_tunnel_id = cf_tunnel_creds.get('TunnelID')
            if cf_tunnel_id:
                active_cf_tunnel_ids.append(cf_tunnel_id)

        # if there are cf tunnels that are not in our redis records,
        # delete them.

        cf_tunnels = get_all_cf_tunnels()

        existing_cf_tunnel_ids = []
        for cf_tunnel in cf_tunnels:
            existing_cf_tunnel_ids.append(cf_tunnel['id'])
            if cf_tunnel['id'] not in active_cf_tunnel_ids:
                logger.info(
                    f'Deleting unused cf tunnel: {cf_tunnel["id"]}')
                try:
                    delete_cf_tunnel(cf_tunnel['id'])
                except CloudFlareAPIError as e:
                    logger.warning(
                        'Could not delete cf tunnel. Maybe a '
                        'cloudflared instance is still connected.')
                    continue

                existing_cf_tunnel_ids.pop()
                logger.info('Deleted unused cf tunnel.')

        # if there are any dns records not matching existing cf
        # tunnels, delete them.

        all_dns_records = get_all_dns_records(zone_id)
        for dns_record in all_dns_records:
            if dns_record['type'] != 'CNAME':
                continue
            name = dns_record['name']
            if not name.startswith(env.CONNECT_SUBDOMAIN_PREFIX):
                continue
            target = dns_record['content']
            if not target.endswith('.cfargotunnel.com'):
                continue
            cf_tunnel_id = target[:-len('.cfargotunnel.com')]
            if cf_tunnel_id not in existing_cf_tunnel_ids:
                logger.info(f'Deleting unused DNS record: {dns_record["id"]}')
                delete_dns_record(zone_id, dns_record['id'])
                logger.info(f'DNS record deleted.')

        time.sleep(5 if reject else 1)

    logger.info('Done.')


if __name__ == '__main__':
    main()

