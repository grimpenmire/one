#!/bin/sh

set -e

image_tag=grimpen/one:latest
docker build . -t $image_tag

echo "Exporting docker image..."
export_file=$(mktemp /tmp/g.one.tar.XXXXXX)
docker save --output $export_file $image_tag

echo "Importing image into k3s..."
sudo k3s ctr images import $export_file
rm $export_file

manifest_file=$(mktemp /tmp/g.one.yaml.XXXXXX)
cp manifest.yaml $manifest_file

sed -i s/%VERSION%/latest/ $manifest_file

# bit ugly but the best i could do for now. if we every have other
# deployments besides redis that don't use our image, they should be
# added here.
yq -i "select(.kind == \"Deployment\" and .metadata.name != \"redis\").spec.template.spec.containers[].imagePullPolicy=\"Never\"" $manifest_file

local_ctx=local
current_ctx=$(kubectl config current-context)
if [ "$current_ctx" != "local" ]; then
    echo "Current context is '$current_ctx', not '$local_ctx' as expected."
    exit 1
fi

kubectl delete -f $manifest_file || true
kubectl apply -f $manifest_file

rm $manifest_file
