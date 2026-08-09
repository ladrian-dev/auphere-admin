output "aurora_cluster_endpoint" {
  value = aws_rds_cluster.main.endpoint
}

output "aurora_reader_endpoint" {
  value = aws_rds_cluster.main.reader_endpoint
}

output "aurora_master_secret_arn" {
  description = "Secreto gestionado por RDS con la password maestra."
  value       = one(aws_rds_cluster.main.master_user_secret[*].secret_arn)
}

output "valkey_primary_endpoint" {
  value = aws_elasticache_replication_group.valkey.primary_endpoint_address
}

output "media_bucket" {
  value = aws_s3_bucket.media.bucket
}

output "state_blobs_bucket" {
  value = aws_s3_bucket.state_blobs.bucket
}

output "media_bucket_arn" {
  value = aws_s3_bucket.media.arn
}

output "state_blobs_bucket_arn" {
  value = aws_s3_bucket.state_blobs.arn
}

output "media_cdn_domain" {
  value = aws_cloudfront_distribution.media.domain_name
}

output "app_secret_arn" {
  value = aws_secretsmanager_secret.app.arn
}
