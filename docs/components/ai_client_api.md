# AI Client API

Abstract interface for AI client integrations.

## Overview

The `ai_client_api` package defines the provider-agnostic `AiClient` ABC with typed `AiTool` and `TokenUsage` dataclasses.

## Methods

- `send_message(prompt, context)` — basic completion.
- `send_message_with_tools(prompt, tools, context)` — completion with typed tool definitions.
