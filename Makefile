PYTHON ?= uv run --python 3.12

.PHONY: setup lint typecheck test up smoke down migrate-up migrate-down

setup:
	uv sync --python 3.12 --all-groups

lint:
	$(PYTHON) ruff check .

typecheck:
	$(PYTHON) mypy src apps

test:
	$(PYTHON) pytest -q

migrate-up:
	$(PYTHON) alembic upgrade head

migrate-down:
	$(PYTHON) alembic downgrade base

up:
	docker compose --profile local up -d

smoke:
	PYTHONPATH=.:src $(PYTHON) scripts/check_w2_stage1_contracts.py
	PYTHONPATH=.:src $(PYTHON) scripts/smoke.py

down:
	docker compose --profile local down
