.PHONY: up seed api test web

up:
	docker run -d --name metrologic-mongo -p 27017:27017 mongodb/mongodb-atlas-local

seed:
	uv run python -m backend.seed.reset

api:
	uv run uvicorn backend.app.main:app --reload --port 8000

test:
	uv run pytest -q

web:
	cd frontend && npm run dev

