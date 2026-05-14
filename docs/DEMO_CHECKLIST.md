# HW3 Demo Cheat Sheet — Team 9

A scannable bullet list to keep open on a second monitor while recording.
For the full talking-track prose, see `docs/VIDEO_SCRIPT.md`.

Total target: **6–8 minutes**. Each beat maps to a rubric bullet in §11.

---

## 0 · Pre-flight (do this 10 min before recording)

- [ ] **Wake Render** — `curl -I https://os-bmaq.onrender.com/health` returns `200`
- [ ] **Confirm new dashboard is deployed** — open `https://os-bmaq.onrender.com/dashboard`, see *"OSPSD · 09 — Chat Service Telemetry"*
- [ ] **Confirm labeled metrics** — `curl -s https://os-bmaq.onrender.com/metrics/prometheus | grep chat_ai_calls_total`
- [ ] **Start Grafana Alloy locally** so Grafana keeps receiving scrapes during the video — `alloy run observability/alloy-config.alloy`
- [ ] **Tabs prepped in this exact order** so you only switch left→right:
  1. VS Code on `DESIGN.md`
  2. Terminal in `/Users/harshithkoriraj/VS_CODE/OS`
  3. `https://os-bmaq.onrender.com/dashboard`
  4. Grafana Cloud dashboard
  5. GitHub PR #2 (https://github.com/NYU-OSPSD-Team-9/OS/pull/2)
  6. CircleCI latest run on `HW3-final`
- [ ] **Close anything secret** — Grafana Cloud Connections page (API token), Render dashboard env vars, Slack admin, OpenAI/Anthropic console with keys visible
- [ ] **Mute notifications**, full-screen the recording app, set screen resolution to 1080p

---

## Beat 1 · "How it works" (90 s) — §11.1 · 2 pts

**Where:** VS Code on `DESIGN.md` (architecture diagram)

**Hit these points in this order:**

- "Team 9, Slack chat vertical. HW3 layered three new capabilities on HW2."
- Three planes:
  1. **Chat plane** — `ChatClient` ABC consumed from the Shared-API git repo
  2. **AI plane** — `ai_client_api` ABC with **OpenAI + Anthropic** providers, function calling, token cost telemetry, tenacity retries
  3. **Cross-vertical plane** — Team Diamonds (issue tracker) **and** Team 12 (Outlook Calendar), both pulled as `pyproject.toml` git deps, never vendored
- Switch to `pyproject.toml` `[tool.uv.sources]` section — show the three git lines

---

## Beat 2 · Live demo + provider swap (90 s) — §11.2 · 2 pts

**Where:** Terminal + dashboard tab

**Commands to type live:**

```bash
# Health check on the deployed service
curl -s https://os-bmaq.onrender.com/health

# Hit the AI assistant with a natural-language prompt
curl -s -X POST https://os-bmaq.onrender.com/ai/chat \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: $SESSION_ID" \
  -d '{"prompt":"Schedule a 30 min sync tomorrow at 3pm titled Team standup"}'
```

**Talk while running:**

- "AI decided to call `schedule_event`, dispatched into the Team-12 Calendar interface"
- "Demo calendar is in-memory, gated by `CALENDAR_DEMO_MODE=true`"

**Provider swap:**

- Open `components/chat_client_service/src/chat_client_service/main.py` → search `_build_issue_client`
- "Resolution order: Diamonds → Jira HTTP → legacy. Swap is environment-driven, no code change"
- Run a test that proves it:

```bash
uv run pytest tests/integration/test_diamonds_cross_vertical.py -v
```

---

## Beat 3 · CircleCI walkthrough (75 s) — §11.3 · 2 pts

**Where:** CircleCI latest run for `HW3-final`

**Show in order:**

- Two jobs: **test** and **deploy**
- Test job expanded: `uv sync --all-packages` pulls all three git-sourced interfaces (Shared-API, Diamonds, Team 12 calendar)
- Quality gates: **ruff** (`select = ALL`), **mypy strict**, **pytest** with **90% coverage** threshold from `pyproject.toml`
- Open the Tests dashboard — **173 tests passed**, junit + HTML coverage artifacts uploaded
- Deploy job: posts to `RENDER_DEPLOY_HOOK_URL` (CircleCI context, never committed) — only on `main` or `HW3` branch filter
- "Push → green CI → Render redeploy, zero-touch"

---

## Beat 4 · E2E and integration tests (75 s) — §11.4 · 2 pts

**Where:** VS Code, navigate `tests/`

**Three tiers:**

- **Unit tests** under `components/*/tests/` — mock SDK boundary (OpenAI, Anthropic, Slack, httpx). Fast, isolated, 90%+ coverage.
- **Integration tests** under `tests/integration/` — five suites:
  1. `test_dependency_injection.py` — DI registry resolves SlackClient on import
  2. `test_cross_vertical.py` — `/issues` routes against the legacy ticket adapter
  3. `test_ai_tool_cross_vertical.py` — AI tool-call → ticket flow
  4. `test_diamonds_cross_vertical.py` — AI tool-call → injected Diamonds `IssueTrackerClient`
  5. `test_calendar_cross_vertical.py` — AI tool-call → Team 12 calendar (schedule / list / cancel + 503 path)
- **E2E** under `tests/e2e/test_slack_e2e.py` — black-box against the deployed Render service: `/health`, `/metrics`, `/metrics/prometheus`, `/dashboard`
- "Rubric calls out AI-tool-call → cross-vertical-action — that's covered in 3 of the 5 integration suites"

---

## Beat 5 · Telemetry dashboard (90 s) — §11.5 · 2 pts

**Where:** Grafana Cloud dashboard tab

**Tour each panel:**

- "Telemetry pipeline: Render service emits Prometheus at `/metrics/prometheus`, Grafana Alloy scrapes every 30 s and remote-writes to Grafana Cloud Hosted Prometheus"
- Top row: **Total Requests · Success Rate · Failure Rate · Avg Latency**
- Middle: **Request Rate timeseries** (success vs failed), **Latency over time**
- Bottom: **Per-route × status_class** (the labeled cross-product), **Domain vs Infra error split**
- Bottom right: **AI Calls Total · Token Consumption (prompt vs completion) · Cumulative AI Cost in USD**

**Trigger a live update during the pan:**

```bash
# generate a domain error
curl -s -o /dev/null https://os-bmaq.onrender.com/this-route-does-not-exist
# generate an AI call so cost panels move
curl -s -X POST https://os-bmaq.onrender.com/ai/chat \
  -H "Content-Type: application/json" -H "X-Session-ID: $SESSION_ID" \
  -d '{"prompt":"list current open issues"}'
```

- "Within 30 s you'll see the per-route domain_error bar tick up and the AI cost panel increment by real dollars"

**Also show the in-process `/dashboard`** for ~5 s:

- "Self-hosted ops console at `https://os-bmaq.onrender.com/dashboard` — same data, different audience: this is the at-a-glance live view, Grafana is the historical analysis"

---

## Beat 6 · Wrap (30 s)

- "Six extra-credit items shipped:
  1. **Multi-provider AI** — OpenAI + Anthropic, swappable through `register_ai_client`
  2. **Structured AI outputs** — Pydantic validation with typed domain exceptions
  3. **Resilience** — tenacity retries on OpenAI and HTTP ticket calls, with tests
  4. **Cost/token telemetry** — Prometheus counters + Grafana panels in dollars
  5. **Multi-environment IaC** — Terraform stg/prod stacks with documented promotion path
  6. **Cross-vertical × 2** — Diamonds and Team 12 instead of one"
- "All four quality gates pass on green CI: ruff, mypy strict, pytest at 91% coverage, mkdocs strict build. Thanks for watching."

---

## Do NOT show on camera

- Grafana Cloud → Connections → Access Policies page (API token visible)
- Render dashboard → Environment tab (Slack/OpenAI/Anthropic secrets visible)
- `~/.zshrc` / `~/.bashrc` if it has `export OPENAI_API_KEY=...`
- Terminal prompt with `OPENAI_API_KEY=sk-...` in scrollback — use `clear` first
- Slack workspace admin / OAuth app config
- Any browser tab titled "API keys" — close before starting

If a key flashes on screen, **rotate it immediately** after recording.

---

## After recording

- [ ] Upload video to the submission location your TAs specified
- [ ] Drop the link in the PR #2 description
- [ ] Shut down the Render service if you want to save credits (rubric says fine since CI + code prove deployment)
- [ ] Stop Grafana Alloy locally
- [ ] Rotate the Grafana Cloud API token if it was visible at any point
