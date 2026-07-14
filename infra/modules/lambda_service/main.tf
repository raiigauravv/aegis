# One AEGIS service = one Lambda + one least-privilege role + its own log group
# (created by the observability module and passed in).

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "aegis-${var.env}-${replace(var.name, "_", "-")}"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "logs" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${var.log_group_arn}:*"]
  }
}

resource "aws_iam_role_policy" "logs" {
  name   = "logs"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.logs.json
}

# Service-specific permissions, defined by the caller (least privilege per service).
# attach_policy is a literal bool because count must be plan-time-known.
resource "aws_iam_role_policy" "service" {
  count  = var.attach_policy ? 1 : 0
  name   = "service"
  role   = aws_iam_role.this.id
  policy = var.policy_json
}

resource "aws_lambda_function" "this" {
  function_name = "aegis-${var.env}-${replace(var.name, "_", "-")}"
  role          = aws_iam_role.this.arn
  timeout       = var.timeout
  memory_size   = var.memory_mb
  architectures = var.architectures

  # Zip services (default) vs container-image services (heavy ML deps)
  package_type     = var.image_uri == null ? "Zip" : "Image"
  runtime          = var.image_uri == null ? "python3.12" : null
  handler          = var.image_uri == null ? "handler.lambda_handler" : null
  filename         = var.image_uri == null ? var.zip_path : null
  source_code_hash = var.image_uri == null ? filebase64sha256(var.zip_path) : null
  image_uri        = var.image_uri

  dynamic "image_config" {
    for_each = var.image_command == null ? [] : [1]
    content {
      command = var.image_command
    }
  }

  logging_config {
    log_format = "Text" # aegis_core.tracing emits JSON lines verbatim
    log_group  = var.log_group_name
  }

  environment {
    variables = merge(
      { AEGIS_ENV = var.env, AEGIS_SERVICE = var.name },
      var.env_vars,
    )
  }
}
