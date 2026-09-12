#!/bin/sh
set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Create or adjust user and group to match PUID/PGID
if [ "$(id -u)" = "0" ]; then
    if ! getent group appgroup >/dev/null 2>&1; then
        groupadd -g "$PGID" appgroup 2>/dev/null || true
    fi
    if ! getent passwd appuser >/dev/null 2>&1; then
        useradd -u "$PUID" -g "$PGID" -m -s /bin/sh appuser 2>/dev/null || true
    fi

    # Ensure ownership of config and music mount directories if they exist
    mkdir -p /config /music
    chown -R "$PUID:$PGID" /config /music 2>/dev/null || true

    # Execute with gosu or su-exec
    if command -v gosu >/dev/null 2>&1; then
        exec gosu "$PUID:$PGID" "$@"
    fi
fi

exec "$@"
