.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python
ENV ?= dev
TF_DIR := infra/envs/$(ENV)
BUILD_DIR := build

.PHONY: help setup lint test package bootstrap deploy plan destroy eval seed demo clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv, install dev deps and pre-commit hooks
	python3.12 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "./shared[dev]"
	$(VENV)/bin/pre-commit install

lint: ## Ruff + mypy
	$(VENV)/bin/ruff check shared services
	$(VENV)/bin/ruff format --check shared services
	$(VENV)/bin/mypy shared/aegis_core services

test: lint ## Lint, type-check, and run unit tests
	$(PY) -m pytest shared/tests services -q

package: ## Build Lambda zip artifacts into build/
	rm -rf $(BUILD_DIR) && mkdir -p $(BUILD_DIR)/hello_world
	$(PY) -m pip install --quiet --target $(BUILD_DIR)/hello_world ./shared
	cp services/hello_world/handler.py $(BUILD_DIR)/hello_world/
	cd $(BUILD_DIR)/hello_world && zip -qr ../hello_world.zip .

bootstrap: ## One-time: create Terraform remote state bucket + lock table
	cd infra/bootstrap && terraform init && terraform apply

plan: package ## Terraform plan for $(ENV)
	cd $(TF_DIR) && terraform init && terraform plan

deploy: package ## Terraform apply for $(ENV)
	cd $(TF_DIR) && terraform init && terraform apply

destroy: ## Tear down $(ENV)
	cd $(TF_DIR) && terraform destroy

eval: ## Run the evaluation suite (Phase 9)
	@echo "eval harness arrives in Phase 5/9" && exit 1

seed: ## Seed the knowledge base (Phase 5)
	@echo "KB seeding arrives in Phase 5" && exit 1

demo: ## Run the demo flow (Phase 10)
	@echo "demo arrives in Phase 10" && exit 1

clean:
	rm -rf $(BUILD_DIR) .pytest_cache .mypy_cache .ruff_cache
