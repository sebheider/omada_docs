#!/bin/sh
# Prepare the data volume and drop root privileges.
#
# When started as root (the default), /data is made writable for PUID:PGID and the application is run as
# that user. This keeps bind mounts on a Synology NAS (e.g. /volume1/docker/omada-docs) working without
# manual permission changes. When the container is started with an explicit non-root user, nothing is changed.
set -eu

DATA_DIR="${OMADA_DOCS_DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
  PUID="${PUID:-1000}"
  PGID="${PGID:-1000}"
  mkdir -p "$DATA_DIR"
  if [ "$(stat -c '%u:%g' "$DATA_DIR")" != "$PUID:$PGID" ]; then
    chown -R "$PUID:$PGID" "$DATA_DIR"
  fi
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups --inh-caps=-all -- "$@"
fi

exec "$@"
