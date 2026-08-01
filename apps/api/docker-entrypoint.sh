#!/bin/sh
set -eu

if [ "$#" -gt 0 ] && [ "$1" = "uvicorn" ]; then
  alembic upgrade head
fi

exec "$@"
