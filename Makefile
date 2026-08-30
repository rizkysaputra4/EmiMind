.PHONY: start stop up down migrate seed api worker web lint typecheck test fmt

start:
	./start.sh

stop:
	./stop.sh

up:
	docker compose up -d

down:
	docker compose down

migrate:
	uv run python scripts/apply_migrations.py

seed:
	uv run python scripts/seed_concept_map.py
	uv run python scripts/seed_xbrl_alias.py
	uv run python scripts/seed_peer_groups.py

api:
	uv run uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000

worker:
	uv run arq services.ingest.worker.WorkerSettings

web:
	cd web && pnpm dev

lint:
	uv run ruff check .
	cd web && pnpm lint

typecheck:
	uv run mypy services eval
	cd web && pnpm typecheck

fmt:
	uv run ruff format .
	cd web && pnpm format

test:
	uv run pytest -m "not integration" tests/
