# Knowledge base storage: versioned FAISS index artifacts + ECR for ML containers.

resource "aws_s3_bucket" "knowledge" {
  bucket = "aegis-${var.env}-knowledge-${var.account_id}"
}

resource "aws_s3_bucket_public_access_block" "knowledge" {
  bucket                  = aws_s3_bucket.knowledge.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "knowledge" {
  bucket = aws_s3_bucket.knowledge.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_ecr_repository" "svc" {
  for_each             = toset(var.container_services)
  name                 = "aegis/${var.env}/${each.value}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

# Keep only the 2 most recent images per repo (ECR free tier is 500 MB).
resource "aws_ecr_lifecycle_policy" "svc" {
  for_each   = aws_ecr_repository.svc
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 2 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 2
      }
      action = { type = "expire" }
    }]
  })
}

output "bucket" {
  value = aws_s3_bucket.knowledge.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.knowledge.arn
}

output "repo_urls" {
  value = { for name, repo in aws_ecr_repository.svc : name => repo.repository_url }
}
