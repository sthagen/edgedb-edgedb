#!/bin/bash

set -ex

re="edgedb-([[:digit:]]+(-(dev|alpha|beta|rc)[[:digit:]]+)?).*\.deb"
slot="$(ls artifacts | sed -n -E "s/${re}/\1/p")"

apt-get update
apt install -y ./artifacts/edgedb-common_*_amd64.deb \
               ./artifacts/edgedb-${slot}_*_amd64.deb
su edgedb -c "/usr/lib/x86_64-linux-gnu/edgedb-${slot}/bin/python3 \
              -m edb.tools --no-devmode test /usr/share/edgedb-${slot}/tests \
              -e flake8 --output-format=simple"
echo "Success!"
