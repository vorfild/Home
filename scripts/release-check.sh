#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"

make check
python3 scripts/load-check.py

release_tmp=$(mktemp -d)
trap 'rm -rf "$release_tmp"' EXIT INT TERM
(
  cd apps/api
  DATABASE_URL="sqlite+aiosqlite:///$release_tmp/release.db" \
    ../../.venv/bin/alembic upgrade head
)

for script in scripts/*.sh; do
  sh -n "$script"
done

if command -v docker >/dev/null 2>&1; then
  docker compose config --quiet
  echo "Docker Compose configuration is valid."
else
  .venv/bin/python - <<'PY'
from pathlib import Path

import yaml

configuration = yaml.safe_load(Path("compose.yaml").read_text())
services = set(configuration.get("services", {}))
volumes = set(configuration.get("volumes", {}))
assert services == {"database", "api", "worker", "frontend", "proxy"}, services
assert {"database_data", "user_files", "backup_data", "caddy_data", "caddy_config"} <= volumes
print("Compose YAML has five expected services and persistent volumes.")
PY
  echo "Docker is unavailable; container runtime verification was skipped." >&2
fi
