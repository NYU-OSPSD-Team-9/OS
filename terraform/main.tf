terraform {
  required_version = ">= 1.5"
  required_providers {
    render = {
      source  = "render-oss/render"
      version = ">= 1.3.0"
    }
  }
}

provider "render" {
  # Set RENDER_API_KEY in the environment or pass via -var.
}

# ---------------------------------------------------------------------------
# Chat Client Service — web service on Render
# ---------------------------------------------------------------------------
resource "render_web_service" "chat_client_service" {
  name               = var.service_name
  plan               = var.plan
  region             = var.region
  start_command      = var.start_command
  build_command      = var.build_command
  runtime            = "python"
  health_check_path  = "/health"

  repo_url     = var.repo_url
  branch       = var.branch
  root_dir     = "components/chat_client_service"
  auto_deploy  = true

  env_vars = {
    "SLACK_SCOPES"       = { value = var.slack_scopes }
    "OPENAI_MODEL"       = { value = var.openai_model }
    "CALENDAR_DEMO_MODE" = { value = var.calendar_demo_mode }
    "ENV"                = { value = "production" }
  }

  # Secrets must be set manually in the Render dashboard:
  # SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, SLACK_REDIRECT_URI,
  # OPENAI_API_KEY, TICKET_SERVICE_BASE_URL, TICKET_BOARD_ID

  secret_files = {}
}
