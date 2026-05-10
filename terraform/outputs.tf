output "service_url" {
  description = "Public URL of the deployed chat client service."
  value       = render_web_service.chat_client_service.url
}

output "service_id" {
  description = "Render service ID (used by CircleCI deploy hook)."
  value       = render_web_service.chat_client_service.id
}
