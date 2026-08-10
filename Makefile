PYTHON ?= python3.12
API_DIR := apps/api
WEB_DIR := apps/web
API_VENV := $(API_DIR)/.venv
API_PYTHON := $(API_VENV)/bin/python

.PHONY: install install-api install-web dev dev-api dev-web check check-api check-web \
	format test test-api test-web secrets pre-commit smoke-llm smoke-doubao-search smoke-live \
	compose-config compose-up \
	compose-down compose-integration

install: install-api install-web

install-api:
	$(PYTHON) -m venv $(API_VENV)
	$(API_PYTHON) -m pip install --upgrade pip
	$(API_PYTHON) -m pip install -e "$(API_DIR)[dev]"

install-web:
	npm ci --prefix $(WEB_DIR)

dev:
	$(MAKE) --no-print-directory -j2 dev-api dev-web

dev-api:
	cd $(API_DIR) && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-web:
	npm run dev --prefix $(WEB_DIR)

check: check-api check-web secrets

check-api:
	cd $(API_DIR) && .venv/bin/python -m ruff check .
	cd $(API_DIR) && .venv/bin/python -m ruff format --check .
	cd $(API_DIR) && .venv/bin/python -m mypy app tests

check-web:
	npm run lint --prefix $(WEB_DIR)
	npm run format:check --prefix $(WEB_DIR)
	npm run typecheck --prefix $(WEB_DIR)

format:
	cd $(API_DIR) && .venv/bin/python -m ruff check --fix .
	cd $(API_DIR) && .venv/bin/python -m ruff format .
	npm run format --prefix $(WEB_DIR)

test: test-api test-web

test-api:
	cd $(API_DIR) && .venv/bin/python -m pytest

test-web:
	npm test --prefix $(WEB_DIR)

secrets:
	$(API_VENV)/bin/pre-commit run detect-secrets --all-files

pre-commit:
	$(API_VENV)/bin/pre-commit install

smoke-llm:
	cd $(API_DIR) && .venv/bin/python scripts/llm_smoke.py

smoke-doubao-search:
	cd $(API_DIR) && .venv/bin/python scripts/doubao_search_smoke.py

smoke-live:
	cd $(API_DIR) && LIVE_PROVIDER_SMOKE=1 .venv/bin/python scripts/live_smoke.py

compose-config:
	docker compose -f compose.yaml config

compose-up:
	docker compose -f compose.yaml up --build -d --wait

compose-down:
	docker compose -f compose.yaml down

compose-integration:
	bash scripts/compose-integration.sh
