# NexusAgent — local development shortcuts (Linux / macOS).
# Windows users: use run.bat / setup.bat.

.PHONY: setup install dev up seed migrate down stop logs test test-backend test-frontend clean

## setup / install — copy env files and install backend + frontend deps
setup install:
	./setup.sh

## dev / up — launch the full Docker stack (db, redis, backend, frontend, nginx)
dev up:
	docker compose up -d --build

## seed — create schema + Brightpath demo workspace (runs inside the backend container)
seed:
	docker compose run --rm backend python backend/scripts/seed_demo.py --init-db

## migrate — apply Alembic migrations (production-faithful schema, incl. RLS)
migrate:
	docker compose run --rm backend alembic upgrade head

## down / stop — stop the stack (keeps volumes)
down stop:
	docker compose down

## logs — follow container logs
logs:
	docker compose logs -f

## test — run backend + frontend test suites
test: test-backend test-frontend

test-backend:
	docker compose run --rm backend pytest -q

test-frontend:
	cd frontend && npm run test

## clean — stop the stack and remove volumes (DESTROYS local data)
clean:
	docker compose down -v
