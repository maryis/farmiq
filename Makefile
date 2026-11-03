.PHONY: up down logs test-api test-web lint-api

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f

test-api:
	cd apps/api && pytest -q

test-web:
	cd apps/web && npm run build

lint-api:
	cd apps/api && ruff check app tests
