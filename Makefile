.PHONY: help install test lint format ci-local clean

help:
	@echo "Available commands:"
	@echo "  make install                  - Install all dependencies"
	@echo "  make test-db-setup            - Setup test database"
	@echo "  make test                     - Run all tests"
	@echo "  make test-backend             - Run backend tests (excludes slow tests)"
	@echo "  make test-backend-all         - Run ALL backend tests (includes slow)"
	@echo "  make test-backend-fast        - Run backend tests in parallel (faster)"
	@echo "  make test-backend-unit        - Run only unit tests"
	@echo "  make test-backend-integration - Run only integration tests"
	@echo "  make test-backend-e2e         - Run only e2e tests (excludes slow)"
	@echo "  make test-backend-slow        - Run only slow tests (timeout tests)"
	@echo "  make lint                     - Run all linters"
	@echo "  make format                   - Format all code"
	@echo "  make ci-local                 - Run CI checks locally (requires act)"
	@echo "  make clean                    - Clean build artifacts"

install:
	@echo "Installing backend dependencies..."
	cd backend && pip install -r requirements.txt -r requirements-dev.txt
	@echo "Installing frontend dependencies..."
	cd frontend && npm ci
	@echo "Installing landing dependencies..."
	cd landing && npm ci
	@echo "Installing pre-commit hooks..."
	pip install pre-commit
	pre-commit install
	@echo "✅ All dependencies installed!"

test-db-setup:
	@echo "Setting up test database..."
	cd backend && python scripts/setup_test_db.py

test-backend:
	@echo "Running backend tests (excludes slow tests)..."
	cd backend && pytest -v

test-backend-all:
	@echo "Running ALL backend tests (includes slow tests)..."
	cd backend && pytest -v -m ""

test-backend-fast:
	@echo "Running backend tests (parallel, fast)..."
	cd backend && pytest -v -n auto --dist loadfile

test-backend-unit:
	@echo "Running unit tests only..."
	cd backend && pytest -v -m "unit and not slow"

test-backend-integration:
	@echo "Running integration tests only..."
	cd backend && pytest -v -m "integration and not slow"

test-backend-e2e:
	@echo "Running e2e tests only (excludes slow)..."
	cd backend && pytest -v -m "e2e and not slow"

test-backend-slow:
	@echo "Running only slow tests..."
	cd backend && pytest -v -m slow

test-frontend:
	@echo "⚠️  No frontend tests configured yet"

test: test-backend test-frontend

lint-backend:
	@echo "Linting backend..."
	cd backend && flake8 .
	cd backend && black --check .
	cd backend && isort --check-only .
	cd backend && mypy app --ignore-missing-imports

lint-frontend:
	@echo "Linting frontend..."
	cd frontend && npm run lint
	cd frontend && npx tsc -b --noEmit

lint: lint-backend lint-frontend

format-backend:
	@echo "Formatting backend code..."
	cd backend && black .
	cd backend && isort .

format-frontend:
	@echo "Formatting frontend code..."
	cd frontend && npm run lint -- --fix

format: format-backend format-frontend

ci-local:
	@echo "Running PR checks locally (requires act: https://github.com/nektos/act)..."
	act pull_request -W .github/workflows/pr-checks.yml

docker-build:
	@echo "Building backend Docker image..."
	docker build -t datamap-backend:local backend

docker-test:
	@echo "Starting test services..."
	docker-compose -f docker-compose.test.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo "Running E2E tests..."
	cd backend && pytest -m e2e
	@echo "Cleaning up..."
	docker-compose -f docker-compose.test.yml down -v

clean:
	@echo "Cleaning build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf backend/.coverage backend/htmlcov backend/coverage.xml 2>/dev/null || true
	rm -rf frontend/dist frontend/node_modules/.cache 2>/dev/null || true
	rm -rf landing/dist landing/node_modules/.cache 2>/dev/null || true
	@echo "✅ Cleaned!"
