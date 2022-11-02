#!/bin/sh

set -e

cwd=$(pwd)
cleanup=false
exit_handler () {
    echo "Cleaning up."
    rm -rf $SOURCE_DIR || true
    cd $cwd
}

if [ ! "$#" = 1 ]; then
    echo "usage: $0 <cloudflared-version>"
    exit 1
fi
cfd_version="$1"

trap exit_handler EXIT

SOURCE_DIR=$(mktemp -d -t g.one.XXXXXX)
git clone . $SOURCE_DIR
cd $SOURCE_DIR

docker build client/ -f client/Dockerfile.cfd \
       -t grimpen/cloudflared:${cfd_version} \
       --build-arg=CFD_VERSION=${cfd_version}
docker push grimpen/cloudflared:${cfd_version}

echo "Do not forget to update the client-docker-compose.yml template file with the latest cloudflared version."
