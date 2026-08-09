terraform {
  required_version = ">= 1.8"
  required_providers { google = { source = "hashicorp/google", version = "~> 7.0" } }
}
variable "project_id" { type = string }
variable "region" { type = string, default = "us-central1" }
provider "google" { project = var.project_id, region = var.region }
resource "google_project_service" "apis" {
  for_each = toset(["run.googleapis.com","artifactregistry.googleapis.com","pubsub.googleapis.com","bigquery.googleapis.com","aiplatform.googleapis.com"])
  service = each.value
  disable_on_destroy = false
}
resource "google_artifact_registry_repository" "roadmate" {
  location = var.region
  repository_id = "roadmate"
  format = "DOCKER"
  depends_on = [google_project_service.apis]
}
resource "google_pubsub_topic" "events" { name = "roadmate-events"; depends_on = [google_project_service.apis] }
resource "google_bigquery_dataset" "analytics" { dataset_id = "roadmate"; location = "US"; delete_contents_on_destroy = true }
