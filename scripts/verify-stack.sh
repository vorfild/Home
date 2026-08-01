#!/bin/sh
set -eu

base_url=${1:-http://localhost}

docker compose config --quiet
docker compose up -d --build --wait

curl --fail --silent --show-error "$base_url/health/live" >/dev/null
curl --fail --silent --show-error "$base_url/api/v1/health/ready" >/dev/null
curl --fail --silent --show-error "$base_url/api/v1/setup/status" >/dev/null

docker compose exec -T database sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "INSERT INTO system_metadata (key, value) VALUES ('"'"'persistence_probe'"'"', '"'"'\"ok\"'"'"'::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;"'
docker compose restart database
docker compose up -d --wait
docker compose exec -T database sh -c \
  'test "$(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT value #>> '"'"'{}'"'"' FROM system_metadata WHERE key = '"'"'persistence_probe'"'"';")" = "ok"'

echo "Compose services, health endpoints, migrations and database persistence are verified."
