variable "service_name" {
  description = "Name of the Render web service."
  type        = string
  default     = "chat-client-service"
}

variable "plan" {
  description = "Render plan tier (free, starter, standard, etc.)."
  type        = string
  default     = "free"
}

variable "region" {
  description = "Render deployment region."
  type        = string
  default     = "oregon"
}

variable "repo_url" {
  description = "GitHub repository URL."
  type        = string
  default     = "https://github.com/NYU-OSPSD-Team-9/OS"
}

variable "branch" {
  description = "Git branch to deploy from."
  type        = string
  default     = "HW3"
}

variable "build_command" {
  description = "Command used to build the service on Render."
  type        = string
  default     = <<-EOT
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    cd /opt/render/project/src
    uv sync --all-packages
  EOT
}

variable "start_command" {
  description = "Command used to start the service on Render."
  type        = string
  default     = <<-EOT
    export PATH="$HOME/.local/bin:$PATH"
    export PYTHONPATH="src:../chat_client_api/src:../slack_client_impl/src:../ai_client_api/src:../openai_ai_client_impl/src:../ticket_client_api/src:../http_ticket_client_impl/src"
    uv run uvicorn chat_client_service.main:app --host 0.0.0.0 --port $PORT
  EOT
}

variable "slack_scopes" {
  description = "OAuth scopes requested from Slack."
  type        = string
  default     = "chat:write,channels:read,channels:history,chat:write.public"
}

variable "openai_model" {
  description = "OpenAI model to use for AI completions."
  type        = string
  default     = "gpt-4o-mini"
}
