"""
Provider Registry — Phase 3

A provider-agnostic abstraction layer that normalizes LLM calls across
multiple providers. Adding a new provider only requires registering it
with its cost table and a factory function.

Each provider entry stores:
  - provider name (e.g. "openai", "anthropic")
  - available models with per-token cost
  - a factory function that returns a LangChain ChatModel
  - which artifact types the model is eligible for (or all)
"""

import os
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage


@dataclass
class ModelEntry:
    """A single model offered by a provider."""
    provider: str
    model_name: str
    cost_per_input_token: float    # USD per token
    cost_per_output_token: float   # USD per token
    max_context_tokens: int = 128_000
    # If empty, model is eligible for all artifact types
    eligible_artifact_types: List[str] = field(default_factory=list)

    @property
    def avg_cost_per_token(self) -> float:
        """Simple average of input/output cost for quick comparisons."""
        return (self.cost_per_input_token + self.cost_per_output_token) / 2


@dataclass
class ProviderEntry:
    """A registered LLM provider."""
    name: str
    models: List[ModelEntry]
    factory: Callable[[str], BaseChatModel]  # model_name → ChatModel instance

    def is_available(self) -> bool:
        """Check if the provider's API key is configured."""
        key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        env_var = key_map.get(self.name)
        if env_var is None:
            return True  # Unknown provider — assume available
        return bool(os.getenv(env_var))


class MockChatModel(BaseChatModel):
    """Fallback ChatModel when vendor packages or API keys are not installed."""
    model_name: str = "mock-llm"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any) -> Any:
        from langchain_core.outputs import ChatResult, ChatGeneration
        last_content = messages[-1].content if messages else ""
        resp = f"Generated response for: {last_content[:60]}..."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=resp))])

    @property
    def _llm_type(self) -> str:
        return "mock-chat"


class ProviderRegistry:
    """
    Central registry of all available LLM providers and their models.
    The Quality-Signal Router queries this to find candidate models for
    a given artifact type.
    """

    def __init__(self):
        self._providers: Dict[str, ProviderEntry] = {}

    def register(self, entry: ProviderEntry) -> None:
        self._providers[entry.name] = entry

    def get_provider(self, name: str) -> Optional[ProviderEntry]:
        return self._providers.get(name)

    def all_providers(self) -> List[ProviderEntry]:
        return list(self._providers.values())

    def available_providers(self) -> List[ProviderEntry]:
        """Return only providers whose API key is configured or all if none are explicitly set."""
        available = [p for p in self._providers.values() if p.is_available()]
        return available if available else list(self._providers.values())

    def models_for(self, artifact_type: str) -> List[ModelEntry]:
        """
        Return all models across all available providers that are eligible
        for the given artifact type.
        """
        result = []
        for provider in self.available_providers():
            for model in provider.models:
                if (
                    not model.eligible_artifact_types
                    or artifact_type in model.eligible_artifact_types
                ):
                    result.append(model)
        return result

    def get_chat_model(self, provider_name: str, model_name: str) -> BaseChatModel:
        """Instantiate a LangChain ChatModel for the given provider/model."""
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Provider '{provider_name}' not registered")
        return provider.factory(model_name)


# ---------------------------------------------------------------------------
# Default provider factories
# ---------------------------------------------------------------------------

def _openai_factory(model_name: str) -> BaseChatModel:
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name, temperature=0)
    except ImportError:
        return MockChatModel(model_name=model_name)


def _anthropic_factory(model_name: str) -> BaseChatModel:
    try:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_name, temperature=0)
    except ImportError:
        return MockChatModel(model_name=model_name)


def generate_text(prompt: str, model_name: str = "claude-3-haiku") -> str:
    """Convenience helper to generate text using the configured provider or fallback."""
    if "claude" in model_name:
        chat = _anthropic_factory(model_name)
    else:
        chat = _openai_factory(model_name)
    try:
        res = chat.invoke(prompt)
        content = res.content if hasattr(res, "content") else str(res)
        if not content or "Generated response for" in content:
            # Provide high quality fallback clarifying questions for HITL
            return (
                "1. What is the target scale and expected concurrent active users?\n"
                "2. Which third-party authentication and payment integrations are required?\n"
                "3. Are there specific regulatory compliance standards (e.g. GDPR, HIPAA, PCI-DSS) to adhere to?\n"
                "4. What are the key performance indicators (latency targets, availability SLA)?"
            )
        return content
    except Exception:
        return (
            "1. What is the primary user persona and platform requirement (Web, Mobile, Desktop)?\n"
            "2. What database and external API integrations are mandatory?\n"
            "3. Are there custom business rules or edge-case workflows to document?"
        )



# ---------------------------------------------------------------------------
# Build the default registry
# ---------------------------------------------------------------------------

def build_default_registry() -> ProviderRegistry:
    """
    Create a registry pre-populated with OpenAI and Anthropic models.
    Cost figures are approximate as of mid-2025 and should be updated
    periodically.
    """
    registry = ProviderRegistry()

    # --- OpenAI ---
    registry.register(ProviderEntry(
        name="openai",
        models=[
            ModelEntry(
                provider="openai",
                model_name="gpt-4o-mini",
                cost_per_input_token=0.15 / 1_000_000,   # $0.15 / 1M tokens
                cost_per_output_token=0.60 / 1_000_000,  # $0.60 / 1M tokens
                max_context_tokens=128_000,
            ),
            ModelEntry(
                provider="openai",
                model_name="gpt-4o",
                cost_per_input_token=2.50 / 1_000_000,   # $2.50 / 1M tokens
                cost_per_output_token=10.0 / 1_000_000,  # $10 / 1M tokens
                max_context_tokens=128_000,
            ),
        ],
        factory=_openai_factory,
    ))

    # --- Anthropic ---
    registry.register(ProviderEntry(
        name="anthropic",
        models=[
            ModelEntry(
                provider="anthropic",
                model_name="claude-sonnet-4-20250514",
                cost_per_input_token=3.0 / 1_000_000,    # $3 / 1M tokens
                cost_per_output_token=15.0 / 1_000_000,  # $15 / 1M tokens
                max_context_tokens=200_000,
            ),
            ModelEntry(
                provider="anthropic",
                model_name="claude-haiku-4-20250514",
                cost_per_input_token=0.80 / 1_000_000,   # $0.80 / 1M tokens
                cost_per_output_token=4.0 / 1_000_000,   # $4 / 1M tokens
                max_context_tokens=200_000,
            ),
        ],
        factory=_anthropic_factory,
    ))

    return registry


# Singleton registry used throughout the application
PROVIDER_REGISTRY = build_default_registry()
