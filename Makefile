.PHONY: dev web gateway static api up down worker-chat
COMPOSE := docker compose -f infra/docker/docker-compose.dev.yml

dev:
	pnpm -r --parallel dev

# 개별 앱 실행
web:
	pnpm --filter @tweek-ninja/web dev

gateway:
	pnpm --filter @tweek-ninja/gateway start:dev

static:
	pnpm --filter @tweek-ninja/static dev

codegen:
	pnpm --filter @tweek-ninja/web gql:gen

build-types:
	pnpm -r --filter @tweek/types --filter @tweek/types-zod run build

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
