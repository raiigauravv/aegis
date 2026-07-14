.DEFAULT_GOAL := help
VENV := .venv
PY ?= $(VENV)/bin/python  # CI overrides with the system python: make package PY=python
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
	$(PY) -m pytest shared/tests services bandit -q

# --platform manylinux2014: Lambda runs Linux; native wheels built for macOS
# (pydantic_core etc.) fail to import there.
PIP_LAMBDA_FLAGS := --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12

SERVICES := hello_world ticket_api intake_router bandit_policy mcp_tools

package: ## Build Lambda zip artifacts into build/
	rm -rf $(BUILD_DIR)
	@for svc in $(SERVICES); do \
	  mkdir -p $(BUILD_DIR)/$$svc; \
	  $(PY) -m pip install --quiet --target $(BUILD_DIR)/$$svc $(PIP_LAMBDA_FLAGS) ./shared; \
	  cp services/$$svc/*.py $(BUILD_DIR)/$$svc/; \
	  rm -f $(BUILD_DIR)/$$svc/test_*.py $(BUILD_DIR)/$$svc/__init__.py; \
	  if [ "$$svc" = "ticket_api" ]; then \
	    cp frontend/index.html $(BUILD_DIR)/$$svc/; \
	    cp bandit/notebooks/regret_curves.png $(BUILD_DIR)/$$svc/ 2>/dev/null || true; \
	    cp evals/scorecard.json $(BUILD_DIR)/$$svc/ 2>/dev/null || true; \
	  fi; \
	  if [ "$$svc" = "bandit_policy" ]; then \
	    $(PY) -m pip install --quiet --target $(BUILD_DIR)/$$svc $(PIP_LAMBDA_FLAGS) numpy; \
	    mkdir -p $(BUILD_DIR)/$$svc/bandit_lib && touch $(BUILD_DIR)/$$svc/bandit_lib/__init__.py; \
	    cp bandit/linucb.py bandit/context.py $(BUILD_DIR)/$$svc/bandit_lib/; \
	  fi; \
	  if [ "$$svc" = "mcp_tools" ]; then \
	    $(PY) -m pip install --quiet --target $(BUILD_DIR)/$$svc $(PIP_LAMBDA_FLAGS) pyyaml; \
	    cp services/mcp_tools/allowlists.yaml $(BUILD_DIR)/$$svc/; \
	  fi; \
	  (cd $(BUILD_DIR)/$$svc && zip -qr ../$$svc.zip .); \
	  echo "built $$svc.zip"; \
	done

bootstrap: ## One-time: create Terraform remote state bucket + lock table
	cd infra/bootstrap && terraform init && terraform apply

plan: package ## Terraform plan for $(ENV)
	cd $(TF_DIR) && terraform init && terraform plan

deploy: package ## Terraform apply for $(ENV)
	cd $(TF_DIR) && terraform init && terraform apply

destroy: ## Tear down $(ENV)
	cd $(TF_DIR) && terraform destroy

ACCOUNT := 490004650850
ECR := $(ACCOUNT).dkr.ecr.us-east-1.amazonaws.com

# KMP_DUPLICATE_LIB_OK: faiss + onnxruntime each bundle libomp on macOS; harmless in this
# read-mostly workload and absent on Linux CI.
eval: ## Run the evaluation suite (blocks below thresholds.yaml floors)
	KMP_DUPLICATE_LIB_OK=TRUE $(PY) evals/run_eval.py

seed: ## Regenerate KB docs + golden retrieval set
	$(PY) knowledge/scripts/seed_kb.py

build-index: ## Build the FAISS index from knowledge/docs
	$(PY) knowledge/scripts/build_index.py

publish-index: ## Upload index versions to the knowledge bucket
	aws s3 sync knowledge/index "s3://aegis-$(ENV)-knowledge-$(ACCOUNT)/index"

docker-%: ## Build+push a container service, e.g. make docker-kb_query
	aws ecr get-login-password | docker login --username AWS --password-stdin $(ECR)
	docker build -f services/$*/Dockerfile -t $(ECR)/aegis/$(ENV)/$*:v1 .
	docker push $(ECR)/aegis/$(ENV)/$*:v1

demo: ## Run the demo flow (Phase 10)
	@echo "demo arrives in Phase 10" && exit 1

clean:
	rm -rf $(BUILD_DIR) .pytest_cache .mypy_cache .ruff_cache
