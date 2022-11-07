# One Connect Service

The `One Connect` service, allows you to quickly create a temporary
shadowsocks/v2ray proxy to share with your family and friends. This
proxy can even be run from a normal desktop or laptop computer on
residential Internet. You do not need a server or a domain name, just
an Internet connection.

The proxy traffic passes through your own computer, so there is no
third-party (besides CloudFlare which acts as a CDN) that can observe
your connections. But this also means that your computer needs to be
turned on while the proxy works.

In order to setup the proxy, you can either go to the [connect
website][1] and follow the instructions there, or just follow the
following instructions:

1. Download your personalized `docker-compose.yml` file:

        curl https://connect.grimpen.one/docker-compose.yml >docker-compose.yml

2. Run the docker-compose file:

        docker-compose up

   If you want to allow compose to run in the background, run it with
   `docker-compose up -d`.

3. Point your local browser to `http://localhost:6003`, copy the
   config you need, and share it with others.

[1]: https://connect.grimpen.one
