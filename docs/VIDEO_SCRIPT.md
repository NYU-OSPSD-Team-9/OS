# HW3 Demo Video Script — OSPSD Team 9

**Target length:** 6–8 min. Record at 1080p. Use macOS QuickTime → Screen Recording, or
Loom / OBS. Speak conversationally — these are talking points, not lines to read.

**Before recording — checklist:**

1. Wake the Render service: `curl https://os-bmaq.onrender.com/health` (returns 200).
2. Make sure Alloy is running locally so Grafana keeps getting data:
   `alloy run observability/alloy-config.alloy`.
3. Open the tabs you'll show in this order:
   - Terminal in `/Users/harshithkoriraj/VS_CODE/OS`
   - VS Code with `DESIGN.md`, `components/`, `tests/integration/`
   - Browser tabs: `https://os-bmaq.onrender.com/dashboard` (your in-process dashboard),
     Grafana Cloud dashboard, GitHub PR #1, CircleCI run #11+ (latest)
4. Open the GitHub PR in one tab so you can scroll through the diff.
5. Have a fresh terminal ready with `OPENAI_API_KEY` exported for the live demo.

---

## Beat 1 — "How the project works" (≈90 sec) [§11.1, 2 pts]

Open VS Code on `DESIGN.md`. Walk through the diagram while talking.

> "I'm Harshith, Team 9. This is HW3. We started in HW2 with a Slack-backed
> chat client behind a `ChatClient` ABC. HW3 layered three things on top of
> that: an AI assistant with tool calling, two cross-vertical integrations,
> and full observability — all deployed on Render with Terraform-managed
> infrastructure."

> "The architecture has three planes. The **Chat plane** is HW2 — abstract
> `ChatClient`, Slack implementation, FastAPI service, generated OpenAPI
> client, and a remote adapter. We refactored that to consume our chat
> vertical's shared API, pulled from a separate Shared-API repo via a git
> dependency."

> "The **AI plane** is new. `ai_client_api` is a provider-agnostic ABC with
> typed `AiTool` definitions. `openai_ai_client_impl` is the concrete impl
> that supports OpenAI function calling — and we capture token usage and
> estimated dollar cost on every call for the cost-telemetry extra credit.
> Both register through the same `get_client()` factory pattern as HW1."

> "The **cross-vertical plane** is where we depend on two other teams'
> APIs as live git dependencies — not vendored. Team Diamonds for the
> issue tracker, Team 12 Outlook for calendar. Each is injected via its
> own `register_X_client_factory` DI hook, so swapping providers — or
> swapping in a fake for tests — never touches the AI tool definitions
> or the route handlers."

Point to `pyproject.toml`'s `[tool.uv.sources]` block:

> "These are the published interfaces. `uv sync` resolves them straight
> from each team's HW3 branch — that's what 'depending on another
> vertical's API, declared in pyproject, not vendored ad-hoc' looks like."

---

## Beat 2 — Live demo + provider swap (≈90 sec) [§11.2, 2 pts]

Switch to terminal. Show the live `/health` endpoint, then send an AI prompt
that triggers a tool call.

```bash
curl -s https://os-bmaq.onrender.com/health
```

Then trigger the AI assistant:

```bash
curl -s -X POST https://os-bmaq.onrender.com/ai/chat \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: $SESSION_ID" \
  -d '{"prompt":"Schedule a 30 min sync tomorrow at 3pm titled Team standup"}'
```

> "The AI took my natural-language prompt, decided it needed to call the
> `schedule_event` tool, and dispatched into the Team-12 Calendar
> interface. The actual implementation handling that call is the
> in-memory demo calendar that's gated behind the
> `CALENDAR_DEMO_MODE=true` flag in `render.yaml`."

Now demonstrate the **provider swap**. Open `components/chat_client_service/src/chat_client_service/main.py` and scroll to `_build_issue_client()`:

> "The cross-vertical resolution order is registered Diamonds factory →
> Jira HTTP service → legacy Trello service. To swap providers I just
> change environment variables — no code change needed. Same for the
> Calendar: `register_calendar_client_factory()` accepts any
> `IssueTrackerClient` impl. The integration tests for Diamonds and
> Calendar both inject a fake concrete impl through this same hook
> without changing a single line of `main.py`."

Show the test:

```bash
uv run pytest tests/integration/test_diamonds_cross_vertical.py -v
```

> "Three tests. Each one registers a different `IssueTrackerClient`
> through the DI hook, fires an AI prompt at `/ai/chat`, and verifies
> the cross-vertical action ran end-to-end."

---

## Beat 3 — CircleCI walkthrough (≈75 sec) [§11.3, 2 pts]

Open the latest CircleCI run on the HW3 branch.

> "Every push to HW3 fires this pipeline. Two jobs: **test** and
> **deploy**. The `test` job spins up a Python 3.12 container, installs
> `uv`, runs `uv sync --all-packages` — which pulls our chat vertical
> Shared-API, the Diamonds work-mgmt-client-interface, and the Team 12
> calendar-client-api straight from their HW-3 branches."

Click into the test job, expand the steps:

> "Three quality gates run in order: **ruff** with `select = ALL`,
> **mypy strict**, and **pytest** with branch coverage. Coverage is
> gated at 90% in `pyproject.toml`. We're sitting around 92.7%."

Click into "Run tests with coverage" and show the JUnit results:

> "The test phase covers all tiers: 144 unit and integration tests
> across components and the top-level `tests/integration` directory."

Click into the deploy job:

> "On a green build for `main` or `HW3`, the `deploy` job posts to
> Render's deploy hook URL — pulled from a CircleCI environment
> variable, never committed. That triggers a Render rebuild and zero-
> downtime swap."

---

## Beat 4 — E2E and integration test overview (≈75 sec) [§11.4, 2 pts]

Open VS Code, navigate to `tests/`.

> "Three tiers of tests, each verifying a different layer."

> "**Unit tests** live next to each component under `components/*/tests/`.
> They mock at the SDK boundary — the OpenAI client tests stub the
> `chat.completions.create` call, the Slack tests stub `slack_sdk`, the
> HTTP ticket tests stub `httpx`. These run in milliseconds and give us
> the 90%+ coverage."

> "**Integration tests** live under `tests/integration/`."

Open `test_ai_tool_cross_vertical.py`:

> "This one drives a fake `AiClient` through the real FastAPI app. It
> registers a tool-emitting AI client, posts to `/ai/chat`, and verifies
> the tool dispatch chain reaches the issue tracker. Only the outermost
> HTTP call is mocked."

Open `test_diamonds_cross_vertical.py`:

> "This one goes a level deeper. It registers a concrete
> `IssueTrackerClient` from Team Diamonds' published interface — using
> the real ABC — and asserts the AI tool call reaches our Diamonds
> adapter and the right method on the injected client."

Open `test_calendar_cross_vertical.py`:

> "Same pattern for Team 12's Calendar. Four tests covering schedule /
> list / cancel and a 503 failure mode when the calendar factory is
> unregistered."

> "And **E2E tests** under `tests/e2e/test_slack_e2e.py` hit the actual
> deployed Render service. The pipeline runs them on every push."

---

## Beat 5 — Telemetry dashboard (≈90 sec) [§11.5, 2 pts]

Switch to the **Grafana Cloud** dashboard tab.

> "Telemetry is shipped to Grafana Cloud Hosted Prometheus. Grafana
> Alloy runs locally as the scraper — it pulls
> `https://os-bmaq.onrender.com/metrics/prometheus` every 30 seconds
> and remote-writes to Grafana Cloud's hosted Prometheus. The config is
> versioned at `observability/alloy-config.alloy`; credentials only
> live in environment variables."

Walk through the panels:

> "Top row: total requests, success rate, failure rate, average
> latency. Then the request rate timeseries — split by success and
> failed status. Average latency over time. Per-route by status class —
> 'ok' versus 'domain_error' (4xx) versus 'infra_error' (5xx) — that's
> the breakdown the rubric asks for, distinguishing caller mistakes
> from real outages so alerts don't page on 422s."

Generate a domain error live and watch it appear:

```bash
curl -s -o /dev/null https://os-bmaq.onrender.com/this-route-does-not-exist
```

> "Bottom row is the AI cost telemetry — calls total, prompt versus
> completion token consumption, and cumulative dollar cost computed
> from the OpenAI per-million-tokens rates baked into
> `openai_ai_client_impl`."

Trigger an AI call so the cost panels move:

```bash
curl -s -X POST https://os-bmaq.onrender.com/ai/chat \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: $SESSION_ID" \
  -d '{"prompt":"List the issues currently open"}'
```

> "Within 30 seconds you'll see calls and tokens tick up. The
> `chat_ai_estimated_cost_usd_total` panel shows real dollars."

---

## Beat 6 — Wrap (≈30 sec)

> "Quick wrap on what we built that wasn't required. Three EC items:
> (1) cost telemetry — token usage and approximate USD cost as
> Prometheus counters; (2) resilience — `tenacity` retries with
> exponential backoff around the OpenAI calls and the HTTP ticket
> calls, with explicit no-retry on 4xx caller mistakes — and tests that
> prove fail-twice-then-succeed; (3) two cross-vertical integrations
> instead of one — Diamonds plus Outlook Calendar."

> "All four quality gates pass on green CI: ruff, mypy strict, pytest
> at 92.7% coverage, mkdocs strict build. Thanks for watching."

---

## Common things to **not** do during recording

- Don't show the Grafana token, the OpenAI key, or any Slack secret.
  Run `unset OPENAI_API_KEY` before opening a terminal that will be on
  camera, or use a session env that's already loaded so it's never
  echoed.
- Don't tab into a window with the API token visible (Grafana Cloud's
  Connections page).
- Don't accidentally commit the demo session ID by pasting it into a
  Markdown file.
