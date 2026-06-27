.PHONY: up down logs test lint typecheck format api shell

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

test:
	docker compose run --rm geollm-api pytest

lint:
	docker compose run --rm geollm-api ruff check .

typecheck:
	docker compose run --rm geollm-api mypy src

format:
	docker compose run --rm geollm-api ruff format .

api:
	docker compose up --build geollm-api gee-plugin-api postgis

shell:
	docker compose run --rm geollm-api bash
