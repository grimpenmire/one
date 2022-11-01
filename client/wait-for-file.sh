#!/bin/sh

set -e

if [ -z "$1" ]; then
    echo "Missing file to wait for."
    exit 1
fi

until [ -f "$1" ]
do
     echo "Waiting for file: $1"
     sleep 5
done
echo "File is ready. Launching command..."

shift
"$@"

exit
