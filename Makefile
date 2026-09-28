# ==============================================================================
# City of Laredo Certificate Management System - Developer Commands
# ==============================================================================

.PHONY: help build up down logs shell test lint wiki clean test-worker-queues-docker test-worker-queues-host validate-https

# Default target
help:
	@echo "City of Laredo Development Commands"
	@echo "===================================="
	@echo ""
	@echo "Setup & Build:"
	@echo "  make setup         - Initial setup (copy .env, build)"
	@echo "  make build         - Build all containers"
	@echo "  make build-nc      - Build without cache"
	@echo ""
	@echo "Start & Stop:"
	@echo "  make up            - Start all services"
	@echo "  make up-dev        - Start with dev tools (greenmail, pgadmin)"
	@echo "  make up-logs       - Start and follow logs"
	@echo "  make down          - Stop all services"
	@echo "  make down-v        - Stop and remove volumes"
	@echo "  make restart       - Restart all services"
	@echo ""
	@echo "Logs:"
	@echo "  make logs          - Follow all logs"
	@echo "  make logs-api      - Follow API logs"
	@echo "  make logs-frontend - Follow Frontend logs"
	@echo "  make logs-workers  - Follow worker logs"
	@echo ""
	@echo "Shell Access:"
	@echo "  make shell-api     - Open shell in API container"
	@echo "  make shell-frontend- Open shell in Frontend container"
	@echo "  make shell-db      - Open PostgreSQL shell"
	@echo "  make shell-redis   - Open Redis CLI"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate    - Run database migrations"
	@echo "  make db-reset      - Reset database (destructive)"
	@echo ""
	@echo "Testing & Linting:"
	@echo "  make test          - Run all tests"
	@echo "  make test-cov      - Run tests with coverage"
	@echo "  make lint          - Run linters"
	@echo "  make lint-fix      - Run linters and fix"
	@echo "  make test-worker-queues-docker - Run strict worker queue tests in Docker (authoritative gate)"
	@echo "  make test-worker-queues-host   - Run strict worker queue tests on host (optional preflight)"
	@echo ""
	@echo "Dead-Letter Queues:"
	@echo "  make dlq-list QUEUE=extraction|ocr   - List dead-lettered tasks"
	@echo "  make dlq-replay QUEUE=extraction|ocr - Re-enqueue dead-lettered tasks"
	@echo ""
	@echo "Documentation:"
	@echo "  make wiki          - Build browser wiki at wiki/index.html"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         - Remove containers and volumes"
	@echo "  make prune         - Docker system prune"
	@echo ""
	@echo "Bulk Import:"
	@echo "  make bulk-import-generate  - Generate manifest CSV from simulation"
	@echo "  make bulk-import-dry-run   - Validate import without writing"
	@echo "  make bulk-import           - Run day-one data import"
	@echo ""
	@echo "Status:"
	@echo "  make status        - Show container status"
	@echo "  make health        - Check API health"
	@echo "  make validate-https - Verify HTTPS hardening gates"

# ==============================================================================
# Setup & Build
# ==============================================================================

setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
		echo "Please review and update .env with your settings"; \
	else \
		echo ".env already exists"; \
	fi
	@for var in MINIO_ROOT_PASSWORD PGADMIN_PASSWORD SECRET_KEY; do \
		if ! grep -Eq "^$$var=.+" .env; then \
			echo "Missing required $$var in .env"; \
			echo "Set $$var before running build/start commands."; \
			exit 1; \
		fi; \
	done
	@if grep -Eq '^SECRET_KEY=dev-secret-key-change-in-production$$' .env; then \
		echo "SECRET_KEY is using the insecure placeholder. Set a unique value in .env."; \
		exit 1; \
	fi
	@docker network inspect laredo-network >/dev/null 2>&1 || docker network create laredo-network >/dev/null
	@$(MAKE) build

build:
	docker compose build

build-nc:
	docker compose build --no-cache

# ==============================================================================
# Start & Stop
# ==============================================================================

up:
	docker compose --profile dev-tools --profile email-intake up -d

up-dev:
	docker compose --profile dev-tools --profile email-intake up -d

up-logs:
	docker compose --profile dev-tools --profile email-intake up

down:
	docker compose down

down-v:
	docker compose down -v

restart: down up

rebuild: down build up

# ==============================================================================
# Logs
# ==============================================================================

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api

logs-frontend:
	docker compose logs -f frontend

logs-workers:
	docker compose logs -f extraction-worker ocr-engine scheduler-worker email-intake-worker

# ==============================================================================
# Shell Access
# ==============================================================================

shell-api:
	docker compose exec api /bin/bash

shell-frontend:
	docker compose exec frontend /bin/sh

shell-db:
	docker compose exec postgres psql -U laredo -d laredo_certificates

shell-redis:
	docker compose exec redis redis-cli

# ==============================================================================
# Database
# ==============================================================================

db-migrate:
	docker compose exec api alembic upgrade head

db-migration:
	@read -p "Migration message: " msg; \
	docker compose exec api alembic revision --autogenerate -m "$$msg"

db-reset:
	docker compose exec postgres psql -U laredo -c "DROP DATABASE IF EXISTS laredo_certificates;"
	docker compose exec postgres psql -U laredo -c "CREATE DATABASE laredo_certificates;"
	@$(MAKE) db-migrate

# ==============================================================================
# Bulk Import (Day-One Data Migration)
# ==============================================================================

bulk-import-generate:
	@echo "Generating simulation manifest and assignments CSV..."
	cd SimulationForTesting && python3 -c "\
	import sys; sys.path.insert(0, '.'); \
	from datetime import date; \
	from pathlib import Path; \
	from lib.data_loader import create_loader_from_defaults; \
	from lib.employee_assigner import create_assigner_from_defaults; \
	from lib.certificate_scheduler import create_scheduler_from_defaults; \
	from generate_simulation import write_manifest, write_employee_assignments; \
	loader = create_loader_from_defaults(); loader.load_all(); \
	assigner = create_assigner_from_defaults(reference_date=date(2026, 2, 4), random_seed=42); \
	assignments = assigner.assign_roles(loader.employees); \
	scheduler = create_scheduler_from_defaults(reference_date=date(2026, 2, 4), random_seed=42); \
	scheduled = scheduler.schedule_certificates(assignments); \
	write_manifest(scheduled, Path('output/manifest.csv')); \
	write_employee_assignments(assignments, Path('output/employee_assignments.csv')); \
	print(f'Generated manifest ({len([s for s in scheduled if s.should_generate])} certs) and assignments ({len(assignments)} employees)'); \
	"

bulk-import-dry-run:
	docker compose exec api python3 /data/scripts/bulk_import.py \
		--employees /data/SimulationForTesting/laredo_test_employees_2000_full.xlsx \
		--manifest /data/SimulationForTesting/output/manifest.csv \
		--certificates /data/SimulationForTesting/output/certificates/ \
		--roles-config /data/SimulationForTesting/config/roles.json \
		--assignments /data/SimulationForTesting/output/employee_assignments.csv \
		--dry-run

bulk-import:
	docker compose exec api python3 /data/scripts/bulk_import.py \
		--employees /data/SimulationForTesting/laredo_test_employees_2000_full.xlsx \
		--manifest /data/SimulationForTesting/output/manifest.csv \
		--certificates /data/SimulationForTesting/output/certificates/ \
		--roles-config /data/SimulationForTesting/config/roles.json \
		--assignments /data/SimulationForTesting/output/employee_assignments.csv

# ==============================================================================
# Testing & Linting
# ==============================================================================

test:
	docker compose exec api pytest -v

test-cov:
	docker compose exec api pytest --cov=src --cov-report=html

lint:
	docker compose exec api ruff check src/

lint-fix:
	docker compose exec api ruff check --fix src/

test-worker-queues-host:
	python3 scripts/check_ocr_test_deps.py --profile tesseract --format text
	EXTRACTION_TESTS_REQUIRE_DOCKER=1 EXTRACTION_RETRY_BACKOFF_MAX_SEC=0 python3 -m pytest \
		BackgroundProcessingInstances/ExtractionWorker/tests/test_retry_queueing.py \
		BackgroundProcessingInstances/ExtractionWorker/tests/test_queue_recovery_integration.py \
		-q
	OCR_TESTS_REQUIRE_DEPS=1 OCR_RETRY_BACKOFF_MAX_SEC=0 python3 -m pytest \
		BackgroundProcessingInstances/OcrEngine/tests/test_retry_queueing.py \
		BackgroundProcessingInstances/OcrEngine/tests/test_queue_recovery_integration.py \
		-q

test-worker-queues-docker:
	@set -eu; \
		run_id="$$(date -u +%Y%m%d%H%M%S)-$$$$"; \
		owner_label="com.cityoflaredo.worker-queue-test=$$run_id"; \
		network="worker-queue-test-net-$$run_id"; \
		redis="worker-queue-redis-$$run_id"; \
		extraction_container="worker-queue-extraction-$$run_id"; \
		ocr_container="worker-queue-ocr-$$run_id"; \
		extraction_runtime_image="laredo-extraction-worker:test-runtime-$$run_id"; \
		extraction_test_image="laredo-extraction-worker:queue-test-$$run_id"; \
		ocr_runtime_image="laredo-ocr-worker:test-runtime-$$run_id"; \
		ocr_test_image="laredo-ocr-worker:queue-test-$$run_id"; \
		owned_container() { \
			[ "$$(docker inspect --format '{{ index .Config.Labels "com.cityoflaredo.worker-queue-test" }}' "$$1" 2>/dev/null || true)" = "$$run_id" ]; \
		}; \
		owned_network() { \
			[ "$$(docker network inspect --format '{{ index .Labels "com.cityoflaredo.worker-queue-test" }}' "$$1" 2>/dev/null || true)" = "$$run_id" ]; \
		}; \
		owned_image() { \
			[ "$$(docker image inspect --format '{{ index .Config.Labels "com.cityoflaredo.worker-queue-test" }}' "$$1" 2>/dev/null || true)" = "$$run_id" ]; \
		}; \
		cleanup() { \
			for container in "$$ocr_container" "$$extraction_container" "$$redis"; do \
				if owned_container "$$container"; then \
					docker rm -f "$$container" >/dev/null 2>&1 || true; \
				fi; \
			done; \
			if owned_network "$$network"; then \
				docker network rm "$$network" >/dev/null 2>&1 || true; \
			fi; \
			for image in "$$ocr_test_image" "$$ocr_runtime_image" "$$extraction_test_image" "$$extraction_runtime_image"; do \
				if owned_image "$$image"; then \
					docker image rm -f "$$image" >/dev/null 2>&1 || true; \
				fi; \
			done; \
		}; \
		trap cleanup EXIT; \
		docker build --label "$$owner_label" \
			-f docker/workers/extraction/Dockerfile -t "$$extraction_runtime_image" .; \
		docker build --label "$$owner_label" \
			--build-arg "WORKER_IMAGE=$$extraction_runtime_image" \
			-f docker/workers/extraction/Dockerfile.test -t "$$extraction_test_image" .; \
		docker build --label "$$owner_label" \
			-f docker/workers/ocr/Dockerfile -t "$$ocr_runtime_image" .; \
		docker build --label "$$owner_label" \
			--build-arg "WORKER_IMAGE=$$ocr_runtime_image" \
			-f docker/workers/ocr/Dockerfile.test -t "$$ocr_test_image" .; \
		docker network create --internal --label "$$owner_label" "$$network" >/dev/null; \
		docker run -d --name "$$redis" --label "$$owner_label" \
			--network "$$network" redis:7-alpine >/dev/null; \
		attempt=0; \
		until docker exec "$$redis" redis-cli ping 2>/dev/null | grep -q PONG; do \
			attempt=$$((attempt + 1)); \
			if [ "$$attempt" -ge 50 ]; then \
				echo "Redis did not become ready for worker queue tests" >&2; \
				exit 1; \
			fi; \
			sleep 0.1; \
		done; \
		docker exec "$$redis" redis-cli COMMAND INFO BLMOVE | tr -d '\r' | grep -qi blmove; \
		docker run --rm --name "$$extraction_container" --label "$$owner_label" \
			--network "$$network" \
			-e PYTHONDONTWRITEBYTECODE=1 \
			-e EXTRACTION_TESTS_REQUIRE_DOCKER=1 \
			-e EXTRACTION_RETRY_BACKOFF_MAX_SEC=0 \
			-e EXTRACTION_REDIS_TEST_URL=redis://$$redis:6379/15 \
			--entrypoint python "$$extraction_test_image" \
			-m pytest \
			BackgroundProcessingInstances/ExtractionWorker/tests/test_retry_queueing.py \
			BackgroundProcessingInstances/ExtractionWorker/tests/test_queue_recovery_integration.py \
			-q -o cache_dir=/tmp/pytest_cache; \
		docker run --rm --name "$$ocr_container" --label "$$owner_label" \
			--network "$$network" \
			-e PYTHONDONTWRITEBYTECODE=1 \
			-e OCR_TESTS_REQUIRE_DEPS=1 \
			-e OCR_RETRY_BACKOFF_MAX_SEC=0 \
			-e OCR_REDIS_TEST_URL=redis://$$redis:6379/14 \
			--entrypoint sh "$$ocr_test_image" \
			-lc "python scripts/check_ocr_test_deps.py --profile tesseract --format text && python -m pytest BackgroundProcessingInstances/OcrEngine/tests/test_retry_queueing.py BackgroundProcessingInstances/OcrEngine/tests/test_queue_recovery_integration.py -q -o cache_dir=/tmp/pytest_cache"

dlq-list:
	docker compose exec api python3 /data/scripts/replay_dlq.py $(or $(QUEUE),extraction) list

dlq-replay:
	docker compose exec api python3 /data/scripts/replay_dlq.py $(or $(QUEUE),extraction) replay

verify-runtime-auth:
	bash scripts/run_runtime_auth_checks.sh

verify-project:
	bash scripts/run_project_verification.sh

# ==============================================================================
# Documentation
# ==============================================================================

wiki:
	python3 scripts/build_wiki.py

# ==============================================================================
# Cleanup
# ==============================================================================

clean:
	docker compose down -v --remove-orphans

prune:
	docker system prune -f

# ==============================================================================
# Status
# ==============================================================================

status:
	docker compose ps

health:
	@echo "Checking API health..."
	@curl -sk https://localhost/api/health | python3 -m json.tool || echo "API not responding"

validate-https:
	@bash -eu -o pipefail -c '\
		failures=0; \
		client_cert=docker/tls/certs/api-client/client.crt; \
		client_key=docker/tls/certs/api-client/client.key; \
		pass() { echo "  PASS  $$1"; }; \
		fail() { echo "  FAIL  $$1"; failures=$$((failures + 1)); }; \
		check_https() { \
			label="$$1"; shift; \
			if curl -sfk --connect-timeout 3 "$$@" >/dev/null 2>&1; then pass "$$label"; else fail "$$label"; fi; \
		}; \
		check_mtls() { \
			host="$$1"; path="$$2"; label="https://$$host$$path"; \
			resolve="$$host:443:127.0.0.1"; \
			if curl -sfk --connect-timeout 3 --resolve "$$resolve" "$$label" >/dev/null 2>&1; then \
				fail "$$label accepts clients without a certificate"; \
			else \
				pass "$$label rejects clients without a certificate"; \
			fi; \
			if curl -sfk --connect-timeout 3 --cert "$$client_cert" --key "$$client_key" --resolve "$$resolve" "$$label" >/dev/null 2>&1; then \
				pass "$$label accepts the trusted client certificate"; \
			else \
				fail "$$label rejects the trusted client certificate"; \
			fi; \
		}; \
		check_unpublished() { \
			service="$$1"; port="$$2"; label="$$3"; \
			container="$$(docker compose ps -q "$$service")"; \
			if [ -n "$$container" ] && published="$$(docker port "$$container" "$$port/tcp" 2>/dev/null)" && [ -n "$$published" ]; then \
				fail "$$label publishes port $$port at $$published"; \
			else \
				pass "$$label port $$port is not published"; \
			fi; \
		}; \
		service_running() { docker compose ps --status running --services | grep -qx "$$1"; }; \
		echo "=== Gate 1: HTTPS and mTLS endpoints ==="; \
		check_https "https://localhost" https://localhost; \
		check_https "https://localhost/api/health" https://localhost/api/health; \
		check_mtls api.localhost /health; \
		check_mtls minio.localhost /; \
		if service_running pgadmin; then check_mtls pgadmin.localhost /; else echo "  SKIP  https://pgadmin.localhost (dev-tools profile not running)"; fi; \
		echo; \
		echo "=== Gate 2: private service ports ==="; \
		check_unpublished frontend 3000 frontend; \
		check_unpublished api 8000 api; \
		check_unpublished pgadmin 80 pgadmin; \
		check_unpublished minio 9000 minio-api; \
		check_unpublished minio 9001 minio-console; \
		check_unpublished postgres 5432 postgres; \
		check_unpublished redis 6380 redis; \
		check_unpublished ollama 11434 ollama; \
		check_unpublished clamav 3310 clamav; \
		echo; \
		echo "=== Gate 3: optional local development endpoints ==="; \
		if service_running roundcube; then check_https "Roundcube http://127.0.0.1:9090" http://127.0.0.1:9090; else echo "  SKIP  Roundcube (dev-tools profile not running)"; fi; \
		if service_running greenmail; then check_https "Greenmail http://127.0.0.1:8080" http://127.0.0.1:8080; else echo "  SKIP  Greenmail (dev-tools/email-intake profile not running)"; fi; \
		if [ "$$failures" -ne 0 ]; then echo; echo "HTTPS validation failed: $$failures check(s)" >&2; exit 1; fi; \
	'
