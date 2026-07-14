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
  env = "dev"
  services = [
    "hello_world", "ticket_api", "intake_router", "kb_query",
    "enrich_nlp", "extract_text", "transcribe_audio",
  ]
  container_services = ["kb_query", "enrich_nlp", "extract_text", "transcribe_audio"]
  build              = "${path.module}/../../../build"
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

module "knowledge" {
  source             = "../../modules/knowledge"
  env                = local.env
  account_id         = data.aws_caller_identity.current.account_id
  container_services = local.container_services
}

data "aws_iam_policy_document" "kb_query" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${module.knowledge.bucket_arn}/index/*"]
  }
}

module "kb_query" {
  source         = "../../modules/lambda_service"
  name           = "kb_query"
  env            = local.env
  image_uri      = "${module.knowledge.repo_urls["kb_query"]}:v1"
  architectures  = ["arm64"]
  log_group_name = module.observability.log_group_names["kb_query"]
  log_group_arn  = module.observability.log_group_arns["kb_query"]
  attach_policy  = true
  policy_json    = data.aws_iam_policy_document.kb_query.json
  timeout        = 60
  memory_mb      = 3008 # CPU scales with memory: keeps ONNX cold start under the 30s APIGW cap
  env_vars = {
    INDEX_BUCKET    = module.knowledge.bucket
    INDEX_PREFIX    = "index/v1"
    SCORE_THRESHOLD = "0.35"
  }
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
  statement {
    actions   = ["sqs:SendMessage"]
    resources = values(module.ingestion.stage_queue_arns)
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
    TABLE_NAME           = module.ingestion.table_name
    ENRICH_QUEUE_URL     = module.ingestion.stage_queue_urls["enrich"]
    EXTRACT_QUEUE_URL    = module.ingestion.stage_queue_urls["extract"]
    TRANSCRIBE_QUEUE_URL = module.ingestion.stage_queue_urls["transcribe"]
  }
}

# --- pipeline stage services (container images) --------------------------------

data "aws_iam_policy_document" "enrich_nlp" {
  statement {
    actions   = ["dynamodb:Query", "dynamodb:UpdateItem", "dynamodb:PutItem"]
    resources = [module.ingestion.table_arn]
  }
  statement {
    # the ONLY principal in the account with access to the re-identification map
    actions   = ["dynamodb:PutItem"]
    resources = [module.ingestion.pii_table_arn]
  }
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [module.ingestion.stage_queue_arns["enrich"]]
  }
}

module "enrich_nlp" {
  source         = "../../modules/lambda_service"
  name           = "enrich_nlp"
  env            = local.env
  image_uri      = "${module.knowledge.repo_urls["enrich_nlp"]}:v1"
  architectures  = ["arm64"]
  log_group_name = module.observability.log_group_names["enrich_nlp"]
  log_group_arn  = module.observability.log_group_arns["enrich_nlp"]
  attach_policy  = true
  policy_json    = data.aws_iam_policy_document.enrich_nlp.json
  timeout        = 60
  memory_mb      = 1024
  env_vars = {
    TABLE_NAME     = module.ingestion.table_name
    PII_TABLE_NAME = module.ingestion.pii_table_name
  }
}

data "aws_iam_policy_document" "extract_text" {
  statement {
    actions   = ["dynamodb:Query", "dynamodb:UpdateItem", "dynamodb:PutItem"]
    resources = [module.ingestion.table_arn]
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${module.ingestion.intake_bucket_arn}/*"]
  }
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [module.ingestion.stage_queue_arns["extract"]]
  }
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [module.ingestion.stage_queue_arns["enrich"]]
  }
}

module "extract_text" {
  source         = "../../modules/lambda_service"
  name           = "extract_text"
  env            = local.env
  image_uri      = "${module.knowledge.repo_urls["extract_text"]}:v1"
  architectures  = ["arm64"]
  log_group_name = module.observability.log_group_names["extract_text"]
  log_group_arn  = module.observability.log_group_arns["extract_text"]
  attach_policy  = true
  policy_json    = data.aws_iam_policy_document.extract_text.json
  timeout        = 120
  memory_mb      = 1024
  env_vars = {
    TABLE_NAME       = module.ingestion.table_name
    ENRICH_QUEUE_URL = module.ingestion.stage_queue_urls["enrich"]
  }
}

data "aws_iam_policy_document" "transcribe_audio" {
  statement {
    actions   = ["dynamodb:Query", "dynamodb:UpdateItem", "dynamodb:PutItem"]
    resources = [module.ingestion.table_arn]
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${module.ingestion.intake_bucket_arn}/*"]
  }
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [module.ingestion.stage_queue_arns["transcribe"]]
  }
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [module.ingestion.stage_queue_arns["enrich"]]
  }
}

module "transcribe_audio" {
  source         = "../../modules/lambda_service"
  name           = "transcribe_audio"
  env            = local.env
  image_uri      = "${module.knowledge.repo_urls["transcribe_audio"]}:v1"
  architectures  = ["arm64"]
  log_group_name = module.observability.log_group_names["transcribe_audio"]
  log_group_arn  = module.observability.log_group_arns["transcribe_audio"]
  attach_policy  = true
  policy_json    = data.aws_iam_policy_document.transcribe_audio.json
  timeout        = 300
  memory_mb      = 2048
  env_vars = {
    TABLE_NAME       = module.ingestion.table_name
    ENRICH_QUEUE_URL = module.ingestion.stage_queue_urls["enrich"]
  }
}

# Concurrency budget (account cap is 10 until the support case resolves):
# 4 mappings x max 2 = 8, leaving 2 for ticket_api/kb_query bursts.
resource "aws_lambda_event_source_mapping" "ingest" {
  event_source_arn        = module.ingestion.queue_arn
  function_name           = module.intake_router.function_name
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = 2
  }
}

resource "aws_lambda_event_source_mapping" "stages" {
  for_each = {
    enrich     = module.enrich_nlp.function_name
    extract    = module.extract_text.function_name
    transcribe = module.transcribe_audio.function_name
  }
  event_source_arn        = module.ingestion.stage_queue_arns[each.key]
  function_name           = each.value
  batch_size              = 5
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = 2
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
    kb_query    = module.kb_query
  }
  route_to_integration = {
    "GET /hello"        = "hello_world"
    "POST /tickets"     = "ticket_api"
    "GET /tickets/{id}" = "ticket_api"
    "GET /"             = "ticket_api"
    "GET /kb/search"    = "kb_query"
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
