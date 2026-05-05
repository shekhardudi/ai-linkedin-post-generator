.PHONY: api ui dev test fmt lint sync app legacy-app

PY := uv run python

sync:
	uv sync --python 3.11 --extra dev

api:
	uv run uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	uv run streamlit run ui/streamlit_app.py

# Run both API and UI in parallel for local development.
dev:
	@(trap 'kill 0' INT; \
	  uv run uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload & \
	  uv run streamlit run ui/streamlit_app.py --server.port 8501 & \
	  wait)

test:
	uv run pytest -q

fmt:
	uv run ruff format .
	uv run ruff check . --fix

lint:
	uv run ruff check .
	uv run mypy backend/api backend/core
