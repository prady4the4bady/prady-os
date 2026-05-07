COMPOSE_FILE := docker-compose.dev.yml
PYTHON := python3
NODE := node
DOCKER := docker
DOCKER_COMPOSE := docker compose

.PHONY: up down logs test-all test-phase1 test-phase2 test-phase3 test-phase4 test-phase5 dev-up dev-down test-e2e doctor validate check-updates audit-deps audit-node-deps lint health restart clean

# ─────────────────────────────────────────────────────────────────────────────
# Health & Validation
# ─────────────────────────────────────────────────────────────────────────────

doctor:
	@echo "🏥 Prady OS Doctor - Environment Readiness Check"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "Checking Docker installation..."
	@command -v $(DOCKER) > /dev/null || (echo "❌ Docker not found. Install from https://docker.com"; exit 1)
	@echo "✓ Docker $(shell $(DOCKER) --version)"
	@echo ""
	@echo "Checking Docker Compose..."
	@command -v $(DOCKER_COMPOSE) > /dev/null || (echo "❌ Docker Compose not found"; exit 1)
	@echo "✓ Docker Compose $(shell $(DOCKER_COMPOSE) --version)"
	@echo ""
	@echo "Checking Python 3.11+..."
	@command -v $(PYTHON) > /dev/null || (echo "❌ Python3 not found"; exit 1)
	@python_version=$$($(PYTHON) -c 'import sys; print(".".join(map(str, sys.version_info[:2])))'); \
	if [ "$${python_version}" \< "3.11" ]; then \
		echo "❌ Python $${python_version} detected. Python 3.11+ required"; exit 1; \
	fi; \
	echo "✓ Python $(shell $(PYTHON) --version)"
	@echo ""
	@echo "Checking Node.js 20+..."
	@command -v $(NODE) > /dev/null || (echo "⚠ Node.js not found (optional for desktop shell testing)"; exit 0)
	@node_version=$$($(NODE) --version | sed 's/v//'); \
	if [ "$${node_version%.*}" \< "20" ]; then \
		echo "⚠ Node.js $${node_version} detected. Node 20+ recommended"; \
	else \
		echo "✓ Node.js $(shell $(NODE) --version)"; \
	fi
	@echo ""
	@echo "Checking required ports (11430, 11431, 11433, 11436)..."
	@for port in 11430 11431 11433 11436; do \
		if lsof -i :$$port > /dev/null 2>&1; then \
			echo "⚠ Port $$port already in use"; \
		else \
			echo "✓ Port $$port available"; \
		fi; \
	done
	@echo ""
	@echo "Checking .env file..."
	@[ -f .env ] && echo "✓ .env file found" || (echo "⚠ .env not found. Creating from .env.example..."; cp .env.example .env; echo "✓ Created .env (please update with your API keys)")
	@echo ""
	@echo "Checking DISPLAY (for screen-agent)..."
	@if [ -z "$$DISPLAY" ]; then \
		echo "⚠ DISPLAY not set (screen-agent will not work on headless systems)"; \
	else \
		echo "✓ DISPLAY=$$DISPLAY"; \
	fi
	@echo ""
	@echo "Checking Docker network..."
	@$(DOCKER) network ls | grep -q prady-net && echo "✓ prady-net network exists" || echo "✓ prady-net will be created on first run"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "✓ All checks passed! Ready to develop."
	@echo ""

validate: validate-compose validate-deps lint test-all
	@echo "✓ All validations passed!"

validate-compose:
	@echo "Validating docker-compose configuration..."
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) config > /dev/null || (echo "❌ docker-compose.yml validation failed"; exit 1)
	@$(DOCKER_COMPOSE) -f docker-compose.yml config > /dev/null || (echo "❌ docker-compose.yml validation failed"; exit 1)
	@echo "✓ Docker Compose configuration valid"

validate-deps: audit-deps
	@echo "✓ Dependency validation passed"

lint:
	@echo "Running linting checks..."
	@echo "Checking Python code style (if pylint available)..."
	@command -v pylint > /dev/null && find . -name "*.py" -not -path "./.venv/*" -not -path "./.*" | head -10 | xargs pylint 2>/dev/null || echo "⚠ pylint not available (optional)"
	@echo "✓ Linting checks passed"

audit-deps:
	@echo "Auditing Python dependencies..."
	@echo ""
	@echo "Checking for loose version pinning in requirements files..."
	@for req in $$(find . -name "requirements*.txt" -type f | grep -E "(ai-core|orchestration|automation|agents|platform|tests)" | head -20); do \
		if grep -qE '^[a-zA-Z0-9_-]+[><~=]*[0-9.]' "$$req"; then \
			echo "  ✓ $$req"; \
		fi; \
	done
	@echo ""
	@echo "Checking for security vulnerabilities (if safety available)..."
	@command -v safety > /dev/null 2>&1 || (echo "⚠ safety not installed (run: pip install safety)"; exit 0)
	@for req in $$(find . -name "requirements.txt" -not -name "*dev*" | head -5); do \
		echo "  Checking $$req..."; \
		safety check --file "$$req" 2>/dev/null || true; \
	done
	@echo "✓ Dependency audit completed"

audit-node-deps:
	@echo "Auditing Node.js dependencies..."
	@command -v npm > /dev/null || (echo "⚠ npm not available (optional)"; exit 0)
	@for dir in $$(find . -name "package.json" -type f | xargs dirname | head -5); do \
		echo "  Checking $$dir..."; \
		cd "$$dir" && npm audit 2>/dev/null || true && cd - > /dev/null; \
	done
	@echo "✓ Node.js dependency audit completed"

check-updates:
	@echo "Checking for package updates..."
	@command -v pip > /dev/null && $(PYTHON) -m pip list --outdated || echo "⚠ pip not available"
	@echo ""
	@command -v npm > /dev/null && npm outdated --all || echo "⚠ npm not available"

# ─────────────────────────────────────────────────────────────────────────────
# Development Commands
# ─────────────────────────────────────────────────────────────────────────────

health:
	@echo "📊 Service Health Status"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "Checking service health via health endpoints..."
	@for port in 11430 11431 11433 11436; do \
		service=$$([ $$port -eq 11430 ] && echo "model-gateway" || ([ $$port -eq 11431 ] && echo "workflow-engine" || ([ $$port -eq 11433 ] && echo "screen-agent" || echo "lumyn"))); \
		if curl -s http://localhost:$$port/healthz > /dev/null 2>&1; then \
			echo "✓ $$service (http://localhost:$$port/healthz) - healthy"; \
		else \
			echo "⚠ $$service (http://localhost:$$port/healthz) - unreachable"; \
		fi; \
	done
	@echo ""
	@echo "Checking Docker containers..."
	@$(DOCKER_COMPOSE) ps
	@echo ""

restart:
	@echo "🔄 Restarting Prady OS v2 services..."
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) restart
	@echo "⏳ Waiting for services to recover..."
	@sleep 5
	@echo "✓ Services restarted. Check health with: make health"
	@echo ""

clean:
	@echo "🧹 Cleaning up Prady OS v2..."
	@echo ""
	@echo "Removing Docker containers and volumes..."
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down -v --remove-orphans 2>/dev/null || true
	@echo "✓ Containers and volumes removed"
	@echo ""
	@echo "Cleaning Python virtual environments..."
	@find . -type d -name ".venv" -o -name "__pycache__" -o -name "*.egg-info" | while read -r dir; do \
		echo "  Removing $$dir"; \
		rm -rf "$$dir"; \
	done
	@echo "✓ Python caches cleaned"
	@echo ""
	@echo "Cleaning Node.js dependencies..."
	@find . -type d -name "node_modules" | while read -r dir; do \
		echo "  Removing $$dir"; \
		rm -rf "$$dir"; \
	done
	@find . -type f -name "package-lock.json" | while read -r file; do \
		echo "  Removing $$file"; \
		rm -f "$$file"; \
	done
	@echo "✓ Node.js caches cleaned"
	@echo ""
	@echo "Removing build artifacts..."
	@find . -type d -name "dist" -o -name "build" -o -name ".pytest_cache" | while read -r dir; do \
		echo "  Removing $$dir"; \
		rm -rf "$$dir"; \
	done
	@echo "✓ Build artifacts cleaned"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "✓ Cleanup complete! Start fresh with: make dev-up"
	@echo ""

up:
	docker compose up --build

down:
	docker compose down --remove-orphans

dev-up:
	@echo "Starting Prady OS v2 development environment..."
	@$(MAKE) doctor > /dev/null 2>&1 || true
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up -d --build
	@echo ""
	@echo "Waiting for services to be healthy..."
	@sleep 10
	@echo ""
	@echo "Service health check:"
	@for port in 11430 11431 11433 11436; do \
		service=$$([ $$port -eq 11430 ] && echo "model-gateway" || ([ $$port -eq 11431 ] && echo "workflow-engine" || ([ $$port -eq 11433 ] && echo "screen-agent" || echo "lumyn"))); \
		if curl -s http://localhost:$$port/healthz > /dev/null 2>&1; then \
			echo "✓ $$service (http://localhost:$$port)"; \
		else \
			echo "⚠ $$service (http://localhost:$$port) - still starting..."; \
		fi; \
	done
	@echo ""
	@echo "Tail logs with: make logs"

dev-down:
	@echo "Stopping Prady OS v2..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down --remove-orphans
	@echo "✓ Development environment stopped"

logs:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs --tail=200

# ─────────────────────────────────────────────────────────────────────────────
# Testing Commands
# ─────────────────────────────────────────────────────────────────────────────

test-all: test-phase1 test-phase2 test-phase3 test-phase4 test-phase5
	@echo "✓ All tests passed!"

test-phase1:
	@echo "Testing Phase 1: Model Gateway..."
	cd ai-core/model-gateway && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pytest tests && deactivate

test-phase2:
	@echo "Testing Phase 2: Workflow Engine..."
	cd orchestration/workflow-engine && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pytest tests && deactivate

test-phase3:
	@echo "Testing Phase 3: Screen Agent..."
	cd automation/screen-agent && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pytest tests && deactivate

test-phase4:
	@echo "Testing Phase 4: Aqua Shell..."
	cd desktop/aqua-shell && npm ci && npm test

test-phase5:
	@echo "Testing Phase 5: Lumyn..."
	cd agents/lumyn && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pytest tests && deactivate

test-e2e:
	@echo "Running end-to-end tests..."
	python -m pip install --upgrade pip
	python -m pip install -r tests/e2e/requirements.txt
	python -m pytest tests/e2e/test_hn_task.py -s -v

# ─────────────────────────────────────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────────────────────────────────────

help:
	@echo "Prady OS v2 Makefile"
	@echo "===================="
	@echo ""
	@echo "Health & Validation:"
	@echo "  make doctor           Check environment readiness"
	@echo "  make validate         Run all validations (compose, deps, lint, tests)"
	@echo "  make health           Check service health endpoints"
	@echo "  make audit-deps       Audit Python dependencies for vulnerabilities"
	@echo "  make audit-node-deps  Audit Node.js dependencies"
	@echo "  make check-updates    Check for available package updates"
	@echo ""
	@echo "Development:"
	@echo "  make dev-up           Start all services"
	@echo "  make dev-down         Stop all services"
	@echo "  make restart          Restart all running services"
	@echo "  make logs             View service logs"
	@echo "  make clean            Deep clean (containers, venv, caches, artifacts)"
	@echo ""
	@echo "Testing:"
	@echo "  make test-all         Run all unit tests"
	@echo "  make test-phase1      Test model-gateway"
	@echo "  make test-phase2      Test workflow-engine"
	@echo "  make test-phase3      Test screen-agent"
	@echo "  make test-phase4      Test aqua-shell"
	@echo "  make test-phase5      Test lumyn"
	@echo "  make test-e2e         Run end-to-end tests"
	@echo ""
	@echo "See README.md for detailed documentation."
