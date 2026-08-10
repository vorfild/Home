#!/bin/sh
set -eu

state_file=.domovoy-update-state
if [ ! -f "$state_file" ]; then
  echo "No saved update state; rollback cancelled." >&2
  exit 1
fi

old_ref=$(sed -n '1p' "$state_file")
archive_path=$(sed -n '2p' "$state_file")
case "$old_ref" in
  *[!0-9a-fA-F]*|"") echo "Invalid saved commit." >&2; exit 1 ;;
esac
case "$archive_path" in
  /data/backups/*) ;;
  *) echo "Invalid saved archive path." >&2; exit 1 ;;
esac

# Keep the newer image available long enough to restore its verified insurance archive.
docker compose stop api worker
docker compose run --rm --no-deps --entrypoint python api -m app.backup_cli restore --archive "$archive_path"
git checkout --detach "$old_ref"
docker compose build
docker compose up -d --wait
./scripts/verify-stack.sh http://localhost
echo "Domovoy rolled back to $(git rev-parse --short HEAD)."
