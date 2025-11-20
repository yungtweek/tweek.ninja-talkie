.PHONY: dev web gateway static api up down worker-chat all-node workers start-all
COMPOSE := docker compose -f infra/docker/docker-compose.dev.yml

web:
	pnpm --filter @talkie/web dev

gateway:
	pnpm --filter @talkie/gateway start:dev

llm-gateway:
	@echo "🔧 Building llm-gateway..."
	@cd apps/llm-gateway && go run ./cmd/llm-gateway

static:
	pnpm --filter @talkie/static dev

codegen:
	pnpm --filter @talkie/web gql:gen

build-types:
	pnpm -r --filter @talkie/types --filter @talkie/types-zod run build

build-events:
	pnpm -r --filter @talkie/events-contracts run build


clean:
	pnpm -r run clean || true
	rm -rf node_modules .turbo .eslintcache

docker-up:
	@echo "🚀 Starting containers..."
	@$(COMPOSE) up -d
docker-stop:
	@$(COMPOSE) stop
docker-down:
	@$(COMPOSE) down
docker-start:
	@$(COMPOSE) start
docker-ps:
	@$(COMPOSE) ps
docker-logs:
	@if [ "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		$(COMPOSE) logs -f $(filter-out $@,$(MAKECMDGOALS)); \
	else \
		echo "Usage: make logs [service] (e.g., make logs kafka)"; \
	fi

worker-chat:
	@echo "🚀  Starting Chat Worker (package=chat_worker)..."
	@. .venv/bin/activate && \
	export PYTHONPATH=$$(pwd)/apps/workers && \
	set -a && source apps/workers/chat_worker/.env.local && set +a && \
	python -m chat_worker.main 2>&1

worker-title:
	@echo "🚀  Starting Chat Worker (package=title_worker)..."
	@. .venv/bin/activate && \
	export PYTHONPATH=$$(pwd)/apps/workers && \
	python -m title_worker.main 2>&1



worker-index:
	@echo "🚀  Starting Chat Worker (package=title_worker)..."
	@. .venv/bin/activate && \
	export PYTHONPATH=$$(pwd)/apps/workers && \
	python -m index_worker.main 2>&1
