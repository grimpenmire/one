# grimpen.one

This repository contains the source code for the services on the
[grimpen.one][1] website, as well as some client side code related to
these services.

## Website and Backend Deployment

The entire Kubernetes deployment config is in the `manifest.yaml`
file. The `deploy.sh` script is provided for building and deploying
the services. It needs to code to be deployed to be committed and
tagged with a tag name starting with "v" followed by a version number
(like "v25").

Apart from the configuration in the `manifest.yaml` file, some secrets
and config need also be manually deployed to the Kubernetes
cluster. This only needs to be done once.

Secrets:
 - `api-secret-key`: should contain a key named `secret-key` with a
   long random value used to sign tokens.
 - `cloudflare-api-token`: should contain a key named `token` in which
we store Cloudflare API token. It needs to have edit access to
"Cloudflare Tunnel" and "DNS Records".
 - `connect-subdomain-seed`: should contain a key named `seed` with a
   64-bit integer as value. Used for generating a deterministic but
   hard to predict sequence of sub-domains.

Config Maps:
 - `cloudflare-config`: should contain the following keys:
   + `connect_domain`: The domain to use for Cloudflare tunnels.
   + `account_id`: The Cloudflare account id.
   + `zone_id`: The Cloudflare zone id (for the domain name in
     `connect_domain`).

## Building custom cloudflared image for One Connect

The One Connect docker-compose client needs a slightly customized
cloudflared image. This needs to be built and pushed every time we
want to update to the latest cloudflared version.

Make sure the second FROM directive in `client/Dockerfile.cfd` points
to the [latest cloudflared version][2]. Assuming latest version is
2022.10.3, build our version of the image by running:

    docker build client -f client/Dockerfile.cfd -t grimpen/cloudflared:2022.10.3

And then push it to Docker Hub:

    docker push grimpen/cloudflared:2022.10.3


[1]: https://grimpen.one
[2]: https://hub.docker.com/r/cloudflare/cloudflared/tags
