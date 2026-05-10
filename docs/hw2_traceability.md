# HW2 Traceability

This document maps the HW2 assignment requirements to the changes implemented in this branch. For each item, it explains:

- where the requirement appears in the HW2 document
- what was changed in the repository
- why the change is needed

## Scope

This document describes the changes implemented in the current working tree. It also calls out the assignment items that were intentionally left incomplete because deployment and commit/push work were explicitly deferred.

## Summary

The main HW2 changes in this branch are:

- a real FastAPI service layer
- Slack OAuth handled by the service
- a generated OpenAPI client package
- a service adapter that re-implements `ChatClient` over HTTP
- updated tests, coverage, and static-analysis support
- updated component READMEs and mkdocs pages

## Requirement Mapping

### 1. FastAPI Service

**Where in HW2**

- `The Assignment`
- `1. Build the Core Components and Service`
- `C. The FastAPI Service ([your_service]_service)`

**What was changed**

- Implemented the service in `components/chat_client_service/src/chat_client_service/main.py`
- Added typed endpoints for:
  - `/health`
  - `/auth/sessions`
  - `/auth/login`
  - `/auth/callback`
  - `/auth/sessions/{session_id}`
  - `DELETE /auth/sessions/{session_id}`
  - `/channels`
  - `/messages`

**Why this is needed**

HW2 requires the local implementation to become a deployable microservice. The service is the deployment unit and is the HTTP boundary that lets the rest of the architecture treat “local vs remote” as a location detail instead of an API change.

**Key files**

- `components/chat_client_service/src/chat_client_service/main.py`
- `components/chat_client_service/tests/test_main.py`
- `components/chat_client_service/README.md`

### 2. OAuth 2.0 Instead of the HW1 Token Shortcut

**Where in HW2**

- `Remarks and Increased Expectations`
- `Authentication`
- FAQ entry:
  - `AUTH The authentication in HW1 used InstalledAppFlow... what is the correct approach for HW2?`

**What was changed**

- Replaced the HW1-style “single local token” idea with a service-managed OAuth flow
- Added login redirect and callback handling in the FastAPI service
- Added service-side auth sessions keyed by `session_id`
- Added session-based protection for `/channels` and `/messages` using `X-Session-ID`

**Why this is needed**

The HW2 file is explicit that HW1’s local installed-app flow is not enough for a web service. A deployed or deployable service needs browser redirect flow, callback handling, server-side token exchange, and stored session state so the service can act on behalf of the authenticated user.

**Key files**

- `components/chat_client_service/src/chat_client_service/main.py`
- `components/chat_client_service/tests/test_main.py`

### 3. Auto-Generated Client

**Where in HW2**

- `The Assignment`
- `1. Build the Core Components and Service`
- `D. The Auto-Generated Client ([your_service]_service_api_client)`

**What was changed**

- Generated a new package:
  - `components/chat_client_service_api_client/`
- Added generator config:
  - `openapi-python-client-config.yml`
- Updated workspace configuration so this package is installed and usable inside the monorepo

**Why this is needed**

The assignment asks for a thin, type-safe client generated from the service OpenAPI spec. This is important because it prevents drift between the service contract and the client calls, and it removes handwritten request boilerplate from the adapter layer.

**Key files**

- `components/chat_client_service_api_client/pyproject.toml`
- `components/chat_client_service_api_client/chat_client_service_api_client/...`
- `openapi-python-client-config.yml`

### 4. Service Client Adapter

**Where in HW2**

- `The Assignment`
- `1. Build the Core Components and Service`
- `E. The Service Client Adapter ([your_service]_adapter)`
- sanity check:
  - `If you write a main.py that works by injecting B, it should also work by injecting E.`

**What was changed**

- Added a new package:
  - `components/chat_client_adapter/`
- Implemented `ChatClientServiceAdapter`, which implements the original `ChatClient` contract
- Wrapped the generated service client behind the same three methods:
  - `send_message`
  - `list_channels`
  - `get_messages`
- Added lazy auth bootstrap so the adapter can create and complete a service auth session when needed
- Registered the adapter via dependency injection on import

**Why this is needed**

This is the main HW2 architectural goal: consumers should still code against `ChatClient`, even when the real implementation now lives behind a service boundary. The adapter is what preserves location transparency.

**Key files**

- `components/chat_client_adapter/src/chat_client_adapter/client.py`
- `components/chat_client_adapter/src/chat_client_adapter/__init__.py`
- `components/chat_client_adapter/tests/test_client.py`
- `components/chat_client_adapter/README.md`

### 5. Preserve the Existing Abstract API

**Where in HW2**

- `A. The Abstract API ([your_service]_api) -> You’ve already built this in HW1!`
- `Goal: Create a clean, minimal interface that defines what your service does, not how.`

**What was changed**

- Kept `chat_client_api` as the contract layer
- Continued using the original DTOs and `ChatClient` ABC
- Kept dependency injection as the shared entry point
- Updated docs so the API package now clearly documents both local and remote implementations

**Why this is needed**

The abstract API is the anchor for the entire HW2 architecture. Without preserving that contract, there is no adapter pattern and no “same consumer code, different geography” design.

**Key files**

- `components/chat_client_api/src/chat_client_api/client.py`
- `components/chat_client_api/README.md`
- `docs/components/chat_client_api.md`

### 6. Keep the Concrete Slack Implementation Usable

**Where in HW2**

- `B. The Concrete Implementation ([your_service]_impl) -> You’ve already built this in HW1!`
- `Goal: This package contains the core business logic and interacts directly with the third-party service.`

**What was changed**

- Kept `slack_client_impl` as the direct Slack business-logic layer
- Cleaned up the implementation to avoid the old `mypy` ignore in the message-history path
- Updated its README/docs to describe the real implemented behavior instead of the old scaffold wording

**Why this is needed**

The service should expose the core implementation, not duplicate it. Keeping this layer intact preserves separation of concerns: the Slack logic stays in one place, and the service layer focuses on HTTP, auth, and serialization.

**Key files**

- `components/slack_client_impl/src/slack_client_impl/client.py`
- `components/slack_client_impl/README.md`
- `docs/components/slack_client_impl.md`

### 7. `/health` Endpoint

**Where in HW2**

- `2. Deployment`
- `Your deployment must include a /health endpoint returning HTTP 200 OK`

**What was changed**

- Added `GET /health` returning `{"status": "ok"}`
- Added tests for it

**Why this is needed**

Even before deployment, the service should expose an operational probe endpoint. This is standard for CI/CD, cloud runtimes, and load balancers.

**Key files**

- `components/chat_client_service/src/chat_client_service/main.py`
- `components/chat_client_service/tests/test_main.py`

### 8. Testing, Coverage, Ruff, and MyPy

**Where in HW2**

- `Remarks and Increased Expectations`
- `MyPy and Ruff`
- `Checklist on Motions`
- `Testing and Coverage`

**What was changed**

- Added tests for the new service and adapter layers
- Updated the root workspace config so the new packages participate in the project
- Ensured:
  - `ruff` passes
  - `mypy` passes in strict mode
  - coverage remains above the root threshold
- Added targeted root config handling for the generated client package so generated code does not pollute handwritten-code quality checks

**Why this is needed**

HW2 explicitly raises the bar on engineering quality. The new architecture adds more moving parts, so tests and static analysis are necessary to keep the code safe and reviewable.

**Key files**

- `pyproject.toml`
- `components/chat_client_adapter/tests/test_client.py`
- `components/chat_client_service/tests/test_main.py`
- `uv.lock`

### 9. uv Workspace and Monorepo Updates

**Where in HW2**

- `Checklist on Motions`
- `uv: uv is your package manager. No requirements.txt or pip. pyproject.toml only.`

**What was changed**

- Updated the root workspace members to include:
  - `chat_client_adapter`
  - `chat_client_service_api_client`
- Updated dev dependencies for docs generation and OpenAPI client generation

**Why this is needed**

Once HW2 adds new packages, the monorepo has to know about them. Otherwise, imports, tests, and CI commands will fail or silently ignore the new components.

**Key files**

- `pyproject.toml`
- `uv.lock`

### 10. Documentation and mkdocs

**Where in HW2**

- `Checklist on Motions`
- `Documentation`
- FAQ:
  - `Do we need to update the mkdocs navigation to include HW2 content...?`
  - answer: `Yes`

**What was changed**

- Rewrote the root `README.md` for the HW2 architecture
- Added or updated component READMEs
- Added new mkdocs pages for:
  - service
  - generated client
  - adapter
- Updated:
  - `docs/index.md`
  - `docs/architecture.md`
  - `docs/design.md`
  - `docs/contributing.md`
  - `mkdocs.yml`

**Why this is needed**

HW2 explicitly requires the documentation set to reflect the new service-based architecture. The old HW1 docs no longer matched the codebase, so they had to be rewritten.

**Key files**

- `README.md`
- `mkdocs.yml`
- `docs/`
- component `README.md` files

## Items Intentionally Left Incomplete

### 11. Public Deployment

**Where in HW2**

- `2. Deployment`
- public cloud requirement
- public base URL requirement
- automatic deployment requirement

**Status in this branch**

- Not completed

**Reason**

You explicitly asked not to deploy yet. The codebase is structured for deployment, but the actual public URL, cloud config, secret setup, and deploy execution were intentionally deferred.

### 12. CircleCI Auto-Deploy

**Where in HW2**

- `2. Deployment`
- `Set up automatic deployment using CircleCI so that every push to your hw2 branch triggers a new build and deployment.`

**Status in this branch**

- Not completed

**Reason**

You explicitly asked not to deploy yet. I kept the project in a deployable state locally, but I did not add or activate cloud deployment jobs.

## Why the Overall Architecture Exists

The HW2 file is pushing one core idea: the consumer should depend on the interface, not on where the implementation runs.

That is why the architecture now has these layers:

- `chat_client_api`
  - stable contract
- `slack_client_impl`
  - local business logic
- `chat_client_service`
  - deployable HTTP boundary
- `chat_client_service_api_client`
  - typed client generated from the service contract
- `chat_client_adapter`
  - re-exposes the remote service as the same original interface

This lets the same client code work with either the direct local implementation or the remote service implementation.
