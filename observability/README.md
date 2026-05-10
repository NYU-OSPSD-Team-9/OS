# Observability Bootstrap

The chat service exposes Prometheus-format metrics at
`/metrics/prometheus`. This directory documents how those metrics flow into
Grafana Cloud and how the dashboard is built.

## Pipeline

```
Render service /metrics/prometheus
            ▲ scrape every 30s
   Grafana Alloy (local agent)
            │ remote_write
            ▼
   Grafana Cloud Hosted Prometheus
            ▼
        Grafana dashboard
```

## Local agent setup

1. Install Alloy:

   ```bash
   brew install grafana/grafana/alloy
   ```

2. Set the Grafana Cloud credentials in your shell (these come from
   Grafana Cloud → Connections → Hosted Prometheus metrics):

   ```bash
   export GC_PROM_URL="https://prometheus-prod-XX-prod-us-central-0.grafana.net/api/prom/push"
   export GC_PROM_USER="123456"
   export GC_PROM_TOKEN="glc_..."
   ```

3. Run the agent:

   ```bash
   alloy run observability/alloy-config.alloy
   ```

   Alloy will scrape the deployed Render service every 30 s and push
   the time series to Grafana Cloud. Leave it running while recording
   the demo video.

## Dashboard

The pre-built dashboard JSON lives at `observability/dashboard.json`.
Import it into Grafana Cloud via Dashboards → New → Import.

The dashboard panels visualize:

- Total requests (rate per minute)
- Success rate (%)
- Failure rate broken down into 4xx (domain) and 5xx (infrastructure)
- Average latency by route + method
- Per-route request counts with status_class labels

All panels query the metrics emitted by the chat service's telemetry
middleware (`chat_requests_total`, `chat_requests_by_route_total`,
`chat_request_latency_ms_avg`, etc.).

## Security

- Credentials live in environment variables only; never commit them.
- The Grafana Cloud API token has write-only scope (metrics push).
- Rotate the token from Grafana Cloud → Account → Access Policies if it
  ever leaks.
