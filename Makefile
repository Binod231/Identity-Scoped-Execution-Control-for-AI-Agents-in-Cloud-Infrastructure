.PHONY: setup venv install localstack-up localstack-down run-proxy test test-integration run-experiments analyze clean help

PYTHON := python3
VENV := .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
UVICORN := $(VENV)/bin/uvicorn

help: ## Show this help message
	@echo "ScopeGuard — Identity-Scoped Execution Control for AI Agents"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: venv install ## Full setup: create venv and install dependencies
	@echo "✅ Setup complete. Activate with: source .venv/bin/activate"

venv: ## Create Python virtual environment
	$(PYTHON) -m venv $(VENV)

install: ## Install dependencies into venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -e ".[dev]"

localstack-up: ## Start LocalStack via Docker Compose
	docker compose up -d
	@echo "⏳ Waiting for LocalStack to be ready..."
	@sleep 10
	@curl -s http://localhost:4566/_localstack/health | python3 -m json.tool || echo "⚠️  LocalStack not ready yet"

localstack-down: ## Stop LocalStack
	docker compose down

run-proxy: ## Start the ScopeGuard proxy server
	$(UVICORN) proxy.main:app --host 0.0.0.0 --port 8000 --reload

test: ## Run unit tests
	$(PYTEST) tests/ -v -m "not integration" --tb=short

test-integration: ## Run integration tests (requires LocalStack)
	$(PYTEST) tests/ -v -m integration --tb=short

test-all: ## Run all tests with coverage
	$(PYTEST) tests/ -v --cov=proxy --cov=agent --cov-report=term-missing

run-experiments: ## Run the full experiment suite (200 tasks × 3 configs)
	$(VENV)/bin/python -m experiments.runner

analyze: ## Analyze experiment results and generate charts
	$(VENV)/bin/python -m experiments.analyze

clean: ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage
	rm -rf experiments/results/*.csv experiments/results/*.png
	@echo "🧹 Cleaned"
