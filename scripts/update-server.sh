#!/bin/sh
set -eu

target_ref=${1:-}
case "$target_ref" in
  ""|*[!A-Za-z0-9._/-]*)
    echo "Usage: $0 <tag-or-commit>" >&2
    exit 2
    ;;
esac

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree has local changes; update cancelled." >&2
  exit 1
fi

lock_dir=.domovoy-update-lock
if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "Another update is already running." >&2
  exit 1
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT INT TERM

current_ref=$(git rev-parse HEAD)
archive_path=$(docker compose exec -T api python -m app.backup_cli create --kind insurance | tail -n 1)

state_tmp=.domovoy-update-state.tmp
{
  printf '%s\n' "$current_ref"
  printf '%s\n' "$archive_path"
} > "$state_tmp"
mv "$state_tmp" .domovoy-update-state

git fetch --tags origin
git rev-parse --verify "${target_ref}^{commit}" >/dev/null
git checkout --detach "$target_ref"

if docker compose build && docker compose up -d --wait && ./scripts/verify-stack.sh http://localhost; then
  echo "Domovoy updated to $(git rev-parse --short HEAD)."
  exit 0
fi

echo "Update check failed; starting automatic rollback." >&2
./scripts/rollback-server.sh
exit 1
