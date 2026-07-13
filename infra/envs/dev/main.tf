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

locals {
  env      = "dev"
  services = ["hello_world"]
}

module "observability" {
  source        = "../../modules/observability"
  env           = local.env
  service_names = local.services
}

# --- hello_world Lambda (Phase 1 deploy-pipeline proof) ---------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "hello_world" {
  name               = "aegis-${local.env}-hello-world"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Least privilege: this function may only write to ITS OWN log group. One role
# per Lambda is the project-wide rule (ADR-001 / governance.md).
data "aws_iam_policy_document" "hello_world_logs" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${module.observability.log_group_arns["hello_world"]}:*"]
  }
}

resource "aws_iam_role_policy" "hello_world_logs" {
  name   = "logs"
  role   = aws_iam_role.hello_world.id
  policy = data.aws_iam_policy_document.hello_world_logs.json
}

resource "aws_lambda_function" "hello_world" {
  function_name    = "aegis-${local.env}-hello-world"
  role             = aws_iam_role.hello_world.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = "${path.module}/../../../build/hello_world.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../build/hello_world.zip")
  timeout          = 10
  memory_size      = 128

  logging_config {
    log_format = "Text" # our JSON lines pass through verbatim
    log_group  = module.observability.log_group_names["hello_world"]
  }

  environment {
    variables = {
      AEGIS_ENV     = local.env
      AEGIS_SERVICE = "hello_world"
    }
  }
}

# Public endpoint via API Gateway HTTP API, not a Function URL: this account's
# new-account restrictions 403 all anonymous Function URL invokes (see ADR-003).
resource "aws_apigatewayv2_api" "public" {
  name          = "aegis-${local.env}"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "hello_world" {
  api_id                 = aws_apigatewayv2_api.public.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.hello_world.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "hello_world" {
  api_id    = aws_apigatewayv2_api.public.id
  route_key = "GET /hello"
  target    = "integrations/${aws_apigatewayv2_integration.hello_world.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.public.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "hello_world_apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.hello_world.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.public.execution_arn}/*"
}

output "hello_world_url" {
  value = "${aws_apigatewayv2_api.public.api_endpoint}/hello"
}
