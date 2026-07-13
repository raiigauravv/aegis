terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  # Values supplied by backend.hcl (created after `make bootstrap`):
  #   terraform init -backend-config=backend.hcl
  backend "s3" {
    key = "envs/dev/terraform.tfstate"
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      project = "aegis"
      env     = local.env
      managed = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  env      = "dev"
  services = ["hello_world", "ticket_api", "intake_router"]
  build    = "${path.module}/../../../build"
}

module "observability" {
  source        = "../../modules/observability"
  env           = local.env
  service_names = local.services
}

module "ingestion" {
  source     = "../../modules/ingestion"
  env        = local.env
  account_id = data.aws_caller_identity.current.account_id
}

# --- services ----------------------------------------------------------------

module "hello_world" {
  source         = "../../modules/lambda_service"
  name           = "hello_world"
  env            = local.env
  zip_path       = "${local.build}/hello_world.zip"
  log_group_name = module.observability.log_group_names["hello_world"]
  log_group_arn  = module.observability.log_group_arns["hello_world"]
}

data "aws_iam_policy_document" "ticket_api" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [module.ingestion.queue_arn]
  }
  statement {
    actions   = ["dynamodb:Query"]
    resources = [module.ingestion.table_arn]
  }
}

module "ticket_api" {
  source         = "../../modules/lambda_service"
  name           = "ticket_api"
  env            = local.env
  zip_path       = "${local.build}/ticket_api.zip"
  log_group_name = module.observability.log_group_names["ticket_api"]
  log_group_arn  = module.observability.log_group_arns["ticket_api"]
  attach_policy  = true
  policy_json    = data.aws_iam_policy_document.ticket_api.json
  env_vars = {
    QUEUE_URL  = module.ingestion.queue_url
    TABLE_NAME = module.ingestion.table_name
  }
}

data "aws_iam_policy_document" "intake_router" {
  statement {
    actions   = ["dynamodb:PutItem"]
    resources = [module.ingestion.table_arn]
  }
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [module.ingestion.queue_arn]
  }
}

module "intake_router" {
  source         = "../../modules/lambda_service"
  name           = "intake_router"
  env            = local.env
  zip_path       = "${local.build}/intake_router.zip"
  log_group_name = module.observability.log_group_names["intake_router"]
  log_group_arn  = module.observability.log_group_arns["intake_router"]
  attach_policy  = true
  policy_json    = data.aws_iam_policy_document.intake_router.json
  timeout        = 30 # visibility timeout (60s) stays > 2x this
  env_vars = {
    TABLE_NAME = module.ingestion.table_name
  }
}

resource "aws_lambda_event_source_mapping" "ingest" {
  event_source_arn        = module.ingestion.queue_arn
  function_name           = module.intake_router.function_name
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    # account concurrency is capped at 10 (new-account restriction, ADR-003):
    # leave headroom for ticket_api + hello_world
    maximum_concurrency = 5
  }
}

# --- public API (HTTP API per ADR-003) ----------------------------------------

resource "aws_apigatewayv2_api" "public" {
  name          = "aegis-${local.env}"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.public.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 25
  }
}

locals {
  routes = {
    "GET /hello"        = module.hello_world
    "POST /tickets"     = module.ticket_api
    "GET /tickets/{id}" = module.ticket_api
    "GET /"             = module.ticket_api
  }
  # one integration per distinct function
  integrations = {
    hello_world = module.hello_world
    ticket_api  = module.ticket_api
  }
  route_to_integration = {
    "GET /hello"        = "hello_world"
    "POST /tickets"     = "ticket_api"
    "GET /tickets/{id}" = "ticket_api"
    "GET /"             = "ticket_api"
  }
}

resource "aws_apigatewayv2_integration" "svc" {
  for_each               = local.integrations
  api_id                 = aws_apigatewayv2_api.public.id
  integration_type       = "AWS_PROXY"
  integration_uri        = each.value.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "svc" {
  for_each  = local.route_to_integration
  api_id    = aws_apigatewayv2_api.public.id
  route_key = each.key
  target    = "integrations/${aws_apigatewayv2_integration.svc[each.value].id}"
}

resource "aws_lambda_permission" "apigw" {
  for_each      = local.integrations
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = each.value.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.public.execution_arn}/*"
}

# --- outputs ------------------------------------------------------------------

output "api_base_url" {
  value = aws_apigatewayv2_api.public.api_endpoint
}

output "intake_bucket" {
  value = module.ingestion.intake_bucket
}

output "dlq_url" {
  value = module.ingestion.dlq_url
}
