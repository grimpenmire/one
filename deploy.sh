#!/bin/sh

set -e

cwd=$(pwd)

cleanup=false
error_handler () {
    echo "Cleaning up."
    rm -rf $SOURCE_DIR || true
    cd $cwd
}

startswith() { case $2 in "$1"*) true;; *) false;; esac; }

trap error_handler EXIT

SOURCE_DIR=$(mktemp -d -t g.one.XXXXXX)
git clone . $SOURCE_DIR
cd $SOURCE_DIR

git_tag=$(git describe --tags 2>/dev/null)
if ! startswith "v" "$git_tag"; then
    echo "No version tag at current head"
    exit 1
fi

version=$(echo $git_tag | sed 's/^.//')

existing_version=$(kubectl get cm oneinfo -o json 2>/dev/null | jq -r .data.version) || true
if [ -z "$existing_version" ]; then
    echo "No prior version deployed."
elif [ "$existing_version" = "$version" ]; then
    echo "Version $version already deployed."
    exit 1
fi

image_tag="grimpen/one:${version}"
docker build . -t ${image_tag}

docker push ${image_tag}

# create temp file, open it (once for reading and once for writing),
# and then delete it to make sure it will be cleaned up.
manifest_file=$(mktemp /tmp/g.one.yaml.XXXXXX)
exec 3>"$manifest_file"
exec 4<"$manifest_file"
rm $manifest_file

sed "s/%VERSION%/$version/" manifest.yaml >&3
kubectl apply -f - <&4

if [ -z "$existing_version" ]; then
    kubectl create cm oneinfo --from-literal=version=$version
else
    kubectl patch cm oneinfo --type merge -p "{\"data\": {\"version\": \"$version\"}}"
fi
