.PHONY: help install lint format typecheck test build check load-check release-check compose-up compose-down

help:
	@echo "make install    Install local development dependencies"
	@echo "make check      Run formatting checks, lint, types, tests and frontend build"
	@echo "make load-check Verify declared scale: 20 users, 50k items, 100k task instances"
	@echo "make release-check Run the complete local release gate"
	@echo "make compose-up Build and launch the five production services"

install:
	python3 -m venv .venv
	.venv/bin/pip install -r apps/api/requirements.lock -r apps/api/requirements-dev.lock
	npm --prefix apps/frontend ci

lint:
	.venv/bin/ruff check apps/api
	npm --prefix apps/frontend run lint

format:
	.venv/bin/ruff format apps/api
	npm --prefix apps/frontend run format

typecheck:
	.venv/bin/mypy apps/api/app
	npm --prefix apps/frontend run typecheck

test:
	cd apps/api && ../../.venv/bin/pytest
	npm --prefix apps/frontend run test

build:
	npm --prefix apps/frontend run build

check:
	.venv/bin/ruff format --check apps/api
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test
	$(MAKE) build

load-check:
	python3 scripts/load-check.py

release-check:
	./scripts/release-check.sh

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down
