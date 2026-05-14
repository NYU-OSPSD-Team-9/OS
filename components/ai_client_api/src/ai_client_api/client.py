"""Abstract interface for AI clients."""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, get_type_hints

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class AiClientError(Exception):
    """Base exception for AI client errors."""


class AiToolError(AiClientError):
    """Raised when a tool call fails."""

    def __init__(self, tool_name: str, message: str) -> None:
        """Initialize with tool name and error message."""
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' failed: {message}")


class AiResponseValidationError(AiClientError):
    """Raised when an AI response fails Pydantic validation."""


class AiProviderError(AiClientError):
    """Raised when the AI provider returns an error."""


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class AiTextResponse(BaseModel):
    """Validated AI text response."""

    text: str
    model: str = ""
    finish_reason: str = "stop"


class AiToolCallResponse(BaseModel):
    """Validated AI tool call response."""

    tool_name: str
    arguments: dict[str, Any] = {}
    result: str = ""


def validate_ai_response(text: str, model: str = "") -> AiTextResponse:
    """Validate and wrap an AI text response in a Pydantic model.

    Args:
        text: The raw text response from the AI provider.
        model: The model identifier used for the call.

    Returns:
        Validated AiTextResponse instance.

    Raises:
        AiResponseValidationError: If validation fails.

    """
    try:
        return AiTextResponse(text=text, model=model)
    except ValidationError as exc:
        raise AiResponseValidationError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AiTool:
    """Describes a callable tool the AI model may invoke."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: Callable[..., str] | None = field(default=None, repr=False, compare=False)


@dataclass
class TokenUsage:
    """Token consumption for a single AI call (or accumulated across rounds)."""

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Tool schema auto-generation
# ---------------------------------------------------------------------------

_PYTHON_TYPE_TO_JSON: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


def tool_from_function(
    func: Callable[..., str],
    description: str,
) -> AiTool:
    """Auto-generate an AiTool from a typed Python function signature.

    Args:
        func: A typed Python callable that will serve as the tool handler.
        description: Human-readable description of what the tool does.

    Returns:
        AiTool with auto-generated parameter schema.

    """
    hints = get_type_hints(func)
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}

    for param_name in sig.parameters:
        if param_name == "return":
            continue
        hint = hints.get(param_name)
        if hint is None:
            continue
        type_name = getattr(hint, "__name__", str(hint))
        json_type = _PYTHON_TYPE_TO_JSON.get(type_name, "string")
        properties[param_name] = {
            "type": json_type,
            "description": param_name.replace("_", " "),
        }

    return AiTool(
        name=func.__name__,
        description=description,
        parameters=properties,
        handler=func,
    )


# ---------------------------------------------------------------------------
# Abstract client
# ---------------------------------------------------------------------------


class AiClient(ABC):
    """Abstract base class for AI client implementations."""

    @abstractmethod
    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt to the AI and return its text response."""

    @abstractmethod
    def send_message_with_tools(
        self,
        prompt: str,
        tools: list[AiTool],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt with available tool definitions for function-calling."""

    def get_last_usage(self) -> TokenUsage | None:
        """Return token usage for the most recent call, or None if unavailable."""
        return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class _AiClientRegistry:
    """Holds the registered AI client factory."""

    _factory: Callable[[], AiClient] | None = None

    @classmethod
    def set(cls, factory: Callable[[], AiClient]) -> None:
        """Register an AI client factory."""
        cls._factory = factory

    @classmethod
    def get(cls) -> Callable[[], AiClient] | None:
        """Return the registered factory or None."""
        return cls._factory


def get_ai_client() -> AiClient:
    """Return an instance of the registered AI client.

    Raises:
        RuntimeError: If no AI client implementation is registered.

    """
    factory = _AiClientRegistry.get()
    if factory is None:
        msg = (
            "No AI client implementation registered. "
            "Import an implementation package to register it."
        )
        raise RuntimeError(msg)
    return factory()


def register_ai_client(factory: Callable[[], AiClient]) -> None:
    """Register an AI client factory.

    Args:
        factory: Callable that returns an AiClient instance.

    """
    _AiClientRegistry.set(factory)
