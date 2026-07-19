.PHONY: bootstrap format lint typecheck test coverage component build-ui check e2e \
	benchmark-ci package-smoke container-smoke serve demo clean

UV ?= uv
NPM ?= npm

bootstrap:
	$(UV) sync --frozen
	$(NPM) --prefix frontend ci

format:
	$(UV) run ruff format src tests scripts
	$(UV) run ruff check --fix src tests scripts
	$(NPM) --prefix frontend run typecheck

lint:
	$(UV) run ruff format --check src tests scripts
	$(UV) run ruff check src tests scripts
	$(UV) run mypy src
	$(UV) run bandit -q -r src

typecheck:
	$(NPM) --prefix frontend run typecheck

test:
	$(UV) run pytest -q

coverage:
	$(UV) run pytest --cov=context_loom --cov-report=term-missing -q

component:
	$(NPM) --prefix frontend run test:component

build-ui:
	$(NPM) --prefix frontend run build

check: lint typecheck test component build-ui
	$(UV) run python scripts/check_public_repo.py

e2e: build-ui
	$(NPM) --prefix frontend run test:e2e

benchmark-ci:
	$(UV) run python scripts/benchmark.py --iterations 3 --check

package-smoke: build-ui
	$(UV) build
	$(UV) run python scripts/package_smoke.py

container-smoke:
	./scripts/container_smoke.sh

serve: build-ui
	$(UV) run context-loom serve

demo:
	$(UV) run context-loom demo

clean:
	$(UV) run python scripts/clean_derived.py
