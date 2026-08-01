# Repository guidance

## Scope

This repository contains the self-hosted family application “Домовой”. The durable product
requirements live in `docs/spec.md`; do not duplicate the full specification here.

## Development stages

- Work on exactly one numbered stage from `docs/spec.md` at a time.
- Do not start the next stage without explicit user confirmation.
- Every completed stage must pass formatting, linting, type checking, tests, the production frontend
  build, and the relevant Compose checks.
- Finish each stage with one focused local commit. Do not push, open a pull request, or deploy unless
  the user asks separately.

## Architecture rules

- Keep the five Compose services: `frontend`, `api`, `worker`, `database`, and `proxy`.
- Keep browser-facing traffic behind Caddy. Never publish database, worker, or API ports directly.
- Store timestamps in UTC and present them in the configured IANA timezone.
- Put HTTP routes under `/api/v1` and enforce permissions on the server.
- Make worker jobs idempotent and safe to retry.
- Never log passwords, PINs, session tokens, cookies, file contents, or other secrets.
- Preserve local disk volumes for PostgreSQL, user files, and backups.

## Code quality

- Python: type-annotated FastAPI/SQLAlchemy code, Alembic for every schema change, Ruff and mypy.
- Frontend: strict TypeScript, centralized Russian strings, accessible controls, responsive layout,
  and reduced-motion support.
- Add unit or integration tests with every behavior change.
- Update `README.md` and `docs/architecture.md` when commands, structure, or major decisions change.
