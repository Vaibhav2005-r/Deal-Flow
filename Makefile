.PHONY: up down migrate migrate-init seed test demo-reset lint fmt golden hooks

up:            ## docker compose up --build
	docker compose up --build

down:
	docker compose down -v

migrate:       ## alembic upgrade head
	cd api && alembic upgrade head

migrate-init:  ## generate the FIRST migration (needs postgres running)
	docker compose up -d postgres
	cd api && alembic revision --autogenerate -m "initial schema"

hooks:         ## wire the golden-test pre-push hook
	git config core.hooksPath .githooks

seed:          ## idempotent: drops and rebuilds
	cd api && python -m app.seed

test:          ## full suite
	cd api && python -m pytest -q

golden:        ## §10 only — the pre-push gate, must stay under 2s
	cd api && python -m pytest tests/golden -q

demo-reset:    ## seed + reset to demo state, MUST complete in <10s
	cd api && python -m app.seed --demo

lint:
	cd api && ruff check .

fmt:
	cd api && ruff check --fix . && ruff format .
