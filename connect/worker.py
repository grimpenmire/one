import os
import json
import time
import signal
import logging
from base64 import b64encode
from CloudFlare import CloudFlare
from pyutils import env, defenv, get_redis, config_logging
from api.tunnel import TunnelManager


defenv('CLOUDFLARE_ACCOUNT_ID', str, optional=False)
defenv('CLOUDFLARE_ZONE_ID', str, optional=False)
defenv('MAX_CF_TUNNELS', int, default=500)

keep_running = True
logger = logging.getLogger()

account_id = env.CLOUDFLARE_ACCOUNT_ID
zone_id = env.CLOUDFLARE_ZONE_ID
max_tunnels = env.MAX_CF_TUNNELS

tunnel_name_prefix = 'tunnel-'


def signal_handler(signum, _):
    global keep_running
    keep_running = False

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)


def create_tunnel(connector_id, cf, tunnel_mng):
    logger.info('Creating Cloudflare tunnel...')
    tunnel_name = tunnel_mng.get_tunnel_uid()
    tunnel_secret = b64encode(os.urandom(32)).decode('ascii')
    tunnel = cf.accounts.cfd_tunnel.post(
        account_id,
        data={'name': tunnel_name, 'tunnel_secret': tunnel_secret}
    )

    tunnel_id = tunnel['id']
    logger.info(
        f'Created Cloudflare tunnel: {tunnel_name} ({tunnel_id})')

    logger.info('Configuring Cloudflare tunnel...')
    domain = 'oneconnect.hair'
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
        hostname=hostname,
        path=path,
        cfd_creds=cfd_creds,
        status='ready',
    )


def main():
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
        cf_tunnels = cf.accounts.cfd_tunnel.get(
            account_id, params={'is_deleted': 'false'},
        )
        cf_tunnels = [
            t for t in cf_tunnels
            if t['name'].startswith(tunnel_mng.cf_tunnel_name_prefix)
        ]
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
                    connector_id, status='rejected',
                    reject_reason=reject_reason)
                continue

            logger.info(
                f'Creating tunnel for connector: {connector_id}...')

            create_tunnel(connector_id, cf, tunnel_mng)

        active_cf_tunnel_ids = []
        for key in redis.scan_iter('tunnel:*'):
            _, connector_id = key.split(':', maxsplit=1)
            tunnel = redis.get(f'tunnel:{connector_id}')
            tunnel = json.loads(tunnel)
            cf_tunnel_creds = tunnel.get('cfd_creds', {})
            cf_tunnel_id = cf_tunnel_creds.get('TunnelID')
            if cf_tunnel_id:
                active_cf_tunnel_ids.append(cf_tunnel_id)

        # create a mapping of cf tunnel ids to dns record ids
        all_dns_records = cf.zones.dns_records.get(zone_id)
        dns_record_ids = {}
        for dns_record in all_dns_records:
            if dns_record['content'].endswith('.cfargotunnel.com'):
                cname = dns_record['content']
                cf_tunnel_id = cname[:-len('.cfargotunnel.com')]
                dns_record_ids[cf_tunnel_id] = dns_record['id']

        for cf_tunnel in cf_tunnels:
            if cf_tunnel['id'] not in active_cf_tunnel_ids:
                logger.info(
                    f'Found unused cf tunnel: {cf_tunnel["id"]}')

                logger.info('Deleting cf tunnel...')
                try:
                    cf.accounts.cfd_tunnel.delete(
                        account_id, cf_tunnel['id']
                    )
                except CloudFlare.exceptions.CloudFlareAPIError as e:
                    logger.warning(
                        'Could not delete cf tunnel. Maybe a '
                        'cloudflared instance is still connected.')
                    continue

                dns_record_id = dns_record_ids[cf_tunnel['id']]
                logger.info(f'Deleting DNS record: {dns_record_id}')
                cf.zones.dns_records.delete(zone_id, dns_record_id)

                logger.info('Deleted unused cf tunnel.')

        time.sleep(5 if reject else 1)

    logger.info('Done.')


if __name__ == '__main__':
    main()

