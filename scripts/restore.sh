#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 /path/to/backup.dump" >&2
    exit 2
fi

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-compose.production.yml}
COMPOSE_TLS_FILE=${COMPOSE_TLS_FILE:-compose.tls.yml}
backup_file=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")

if [[ ! -r "$backup_file" ]]; then
    echo "Backup is not readable: $backup_file" >&2
    exit 1
fi

cd "$ROOT_DIR"
compose_args=(-f "$COMPOSE_FILE")
if [[ -n "$COMPOSE_TLS_FILE" && -f "$COMPOSE_TLS_FILE" ]]; then
    compose_args+=(-f "$COMPOSE_TLS_FILE")
fi
if [[ ! -f .env ]]; then
    echo "Missing $ROOT_DIR/.env" >&2
    exit 1
fi

checksum_file="$backup_file.sha256"
if [[ -f "$checksum_file" ]]; then
    (cd "$(dirname "$backup_file")" && sha256sum --check "$(basename "$checksum_file")")
else
    echo "Warning: checksum file not found; validating only the dump structure" >&2
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

docker compose "${compose_args[@]}" exec -T db pg_restore --list < "$backup_file" >/dev/null

echo "This will replace database '$DB_NAME' and stop the backend."
read -r -p "Type RESTORE to continue: " confirmation
if [[ "$confirmation" != "RESTORE" ]]; then
    echo "Restore cancelled"
    exit 1
fi

docker compose "${compose_args[@]}" stop proxy backend
docker compose "${compose_args[@]}" exec -T db dropdb --force --if-exists -U "$DB_USER" "$DB_NAME"
docker compose "${compose_args[@]}" exec -T db createdb -U "$DB_USER" "$DB_NAME"
docker compose "${compose_args[@]}" exec -T db \
    pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --no-privileges \
    < "$backup_file"
docker compose "${compose_args[@]}" up -d backend proxy

echo "Restore completed. Verify /api/health and application data."
