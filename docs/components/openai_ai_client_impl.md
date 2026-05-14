# OpenAI AI Client Implementation

Concrete `OpenAiClient` backed by the OpenAI Python SDK.

## Overview

Implements `AiClient` with function calling, tool round loop capped at 5 rounds, per-call token usage capture, and tenacity-backed retries.

## Configuration

- `OPENAI_API_KEY` — required
- `OPENAI_MODEL` — optional, defaults to `gpt-4o-mini`
