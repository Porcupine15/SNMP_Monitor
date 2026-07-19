#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-compose.production.yml}
COMPOSE_TLS_FILE=${COMPOSE_TLS_FILE:-compose.tls.yml}
BACKUP_DIR=${BACKUP_DIR:-"$ROOT_DIR/backups"}
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}

cd "$ROOT_DIR"
compose_args=(-f "$COMPOSE_FILE")
if [[ -n "$COMPOSE_TLS_FILE" && -f "$COMPOSE_TLS_FILE" ]]; then
    compose_args+=(-f "$COMPOSE_TLS_FILE")
fi
if [[ ! -f .env ]]; then
    echo "Missing $ROOT_DIR/.env" >&2
    exit 1
fi

umask 077
set -a
# shellcheck disable=SC1091
. ./.env
set +a

mkdir -p "$BACKUP_DIR"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$BACKUP_DIR/snmp-monitor-$timestamp.dump"
partial="$target.partial"
trap 'rm -f "$partial"' EXIT

docker compose "${compose_args[@]}" exec -T db \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom --no-owner --no-privileges \
    > "$partial"

docker compose "${compose_args[@]}" exec -T db pg_restore --list < "$partial" >/dev/null
mv "$partial" "$target"
(
    cd "$BACKUP_DIR"
    sha256sum "$(basename "$target")" > "$(basename "$target").sha256"
)
find "$BACKUP_DIR" -type f \( -name '*.dump' -o -name '*.dump.sha256' \) \
    -mtime "+$BACKUP_RETENTION_DAYS" -delete

echo "Backup created and verified: $target"
