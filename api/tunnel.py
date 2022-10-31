import json
from pyutils import env, defenv


defenv('TUNNEL_TTL', int, default=300)


class TunnelManager:
    def __init__(self, redis):
        self.redis = redis
        self.cf_tunnel_name_prefix = 'tunnel-'
        self.tunnel_ttl = env.TUNNEL_TTL

    def get_tunnel(self, connector_id):
        key = f'tunnel:{connector_id}'
        tunnel = self.redis.get(key)
        if tunnel:
            self.redis.expire(key, self.tunnel_ttl)
            return json.loads(tunnel)

        # in case a tunnel is created right after we read the empty
        # key, both writers are going to write the same value, so we
        # don't even need to set nx=True in the set call down below.
        tunnel = {
            'status': 'pending',
            'hostname': None,
            'path': None,
            'cfd_creds': None,
        }
        self.redis.set(key, json.dumps(tunnel))
        return tunnel

    def get_tunnel_uid(self):
        uid = self.redis.incr('uid:tunnel')
        return self.cf_tunnel_name_prefix + str(uid)

    def write_tunnel(self, connector_id, *, hostname=None, path=None,
                     cfd_creds=None, status=None, reject_reason=None):
        data = {
            'status': status,
            'hostname': hostname,
            'path': path,
            'cfd_creds': cfd_creds,
        }
        if reject_reason:
            data['reject_reason'] = reject_reason
        self.redis.set(f'tunnel:{connector_id}', json.dumps(data),
                       ex=self.tunnel_ttl)
