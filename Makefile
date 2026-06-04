.PHONY: help up down dev logs migrate seed test lint

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

up: ## Start all services (production build)
	docker compose up --build -d

down: ## Stop all services
	docker compose down

dev: ## Start with hot-reload
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

logs: ## Tail logs
	docker compose logs -f

migrate: ## Run Alembic migrations
	docker compose exec api alembic upgrade head

revision: ## Create a new migration (usage: make revision MSG="add table")
	docker compose exec api alembic revision --autogenerate -m "$(MSG)"

seed: ## Ingest a sample document for testing
	curl -s -X POST http://localhost:8000/api/v1/documents/ \
	  -H "Content-Type: application/json" \
	  -d '{"title":"Sample Doc","content":"NexusMind is an enterprise AI research platform."}' | python3 -m json.tool

test: ## Run backend tests
	docker compose exec api pytest tests/ -v

lint: ## Lint backend
	docker compose exec api ruff check app/ && mypy app/

crawl: ## Crawl a URL (usage: make crawl URL=https://example.com)
	curl -s -X POST http://localhost:8000/api/v1/documents/crawl \
	  -H "Content-Type: application/json" \
	  -d '{"url":"$(URL)","max_depth":2,"max_pages":20}' | python3 -m json.tool
