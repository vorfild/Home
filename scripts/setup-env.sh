#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_file="$project_root/.env"
app_address=${1:-http://localhost}

if [ -e "$env_file" ]; then
  echo ".env already exists; refusing to overwrite it." >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate installation secrets." >&2
  exit 1
fi

database_password=$(openssl rand -hex 32)
secret_key=$(openssl rand -hex 64)

umask 077
{
  echo "COMPOSE_PROJECT_NAME=domovoy"
  echo "APP_ADDRESS=$app_address"
  echo "APP_TIMEZONE=Europe/Moscow"
  echo "POSTGRES_DB=domovoy"
  echo "POSTGRES_USER=domovoy"
  echo "POSTGRES_PASSWORD=$database_password"
  echo "SECRET_KEY=$secret_key"
  echo "LOG_LEVEL=INFO"
  echo "WORKER_POLL_INTERVAL_SECONDS=30"
} > "$env_file"

echo "Created $env_file with mode 600."
