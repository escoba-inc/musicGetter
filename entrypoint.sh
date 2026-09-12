#!/bin/sh
set -e

# If PUID and PGID are explicitly provided and container is root, drop privileges to match host user
if [ "$(id -u)" = "0" ] && [ -n "$PUID" ] && [ -n "$PGID" ]; then
    if ! getent group appgroup >/dev/null 2>&1; then
        groupadd -g "$PGID" appgroup 2>/dev/null || true
    fi
    if ! getent passwd appuser >/dev/null 2>&1; then
        useradd -u "$PUID" -g "$PGID" -m -s /bin/sh appuser 2>/dev/null || true
    fi

    mkdir -p /config /music
    chown -R "$PUID:$PGID" /config /music 2>/dev/null || true

    if command -v gosu >/dev/null 2>&1; then
        exec gosu "$PUID:$PGID" "$@"
    fi
fi

# Otherwise execute directly
exec "$@"
