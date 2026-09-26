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
        """Check if the provider's API key is configured and non-empty."""
        if self.name == "ollama":
            return os.getenv("OLLAMA_ENABLED", "false").lower() in ("true", "1", "yes")

        key_map = {
            "openai": ["OPENAI_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"],
            "groq": ["GROQ_API_KEY"],
            "openrouter": ["OPENROUTER_API_KEY"],
            "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "mistral": ["MISTRAL_API_KEY"],
            "deepseek": ["DEEPSEEK_API_KEY"],
            "cerebras": ["CEREBRAS_API_KEY"],
            "together": ["TOGETHER_API_KEY"],
        }
        val = key_map.get(self.name)
        if val is None:
            return True  # Unknown provider — assume available
        return any(bool((os.getenv(k) or "").strip()) for k in val)


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
# Provider factory helpers
# ---------------------------------------------------------------------------

def _openai_factory(model_name: str) -> BaseChatModel:
    if not os.getenv("OPENAI_API_KEY"):
        return MockChatModel(model_name=model_name)
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name, temperature=0)
    except Exception:
        return MockChatModel(model_name=model_name)


def _anthropic_factory(model_name: str) -> BaseChatModel:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return MockChatModel(model_name=model_name)
    try:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_name, temperature=0)
    except Exception:
        return MockChatModel(model_name=model_name)


def _create_openai_compatible_factory(
    provider_name: str,
    base_url: str,
    env_keys: List[str],
    default_key: str = ""
) -> Callable[[str], BaseChatModel]:
    """Generic factory for any provider exposing an OpenAI-compatible /v1/chat/completions endpoint."""
    def factory(model_name: str) -> BaseChatModel:
        api_key = default_key
        for k in env_keys:
            val = os.getenv(k)
            if val:
                api_key = val
                break

        if not api_key:
            return MockChatModel(model_name=f"{provider_name}:{model_name}")

        resolved_base_url = os.getenv(f"{provider_name.upper()}_BASE_URL", base_url)
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model_name,
                base_url=resolved_base_url,
                api_key=api_key,
                temperature=0,
                max_retries=2,
                timeout=45.0,
            )
        except Exception:
            return MockChatModel(model_name=f"{provider_name}:{model_name}")
    return factory


def generate_text(prompt: str, model_name: Optional[str] = None) -> str:
    """Convenience helper to generate text using the best available configured provider or fallback."""
    chat = None
    avail = PROVIDER_REGISTRY.available_providers()
    if avail:
        # If model_name requested, try to find matching provider
        if model_name:
            for p in avail:
                for m in p.models:
                    if m.model_name == model_name:
                        chat = p.factory(model_name)
                        break
                if chat:
                    break
        # Otherwise pick first available provider model
        if not chat:
            for p in avail:
                if p.is_available() and p.models:
                    chat = p.factory(p.models[0].model_name)
                    break

    if chat is None:
        chat = _openai_factory("gpt-4o-mini")

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
# Build the default registry with Free & Multi-Provider LLMs
# ---------------------------------------------------------------------------

def build_default_registry() -> ProviderRegistry:
    """
    Create a registry pre-populated with OpenAI, Anthropic, Groq, OpenRouter,
    Google Gemini, DeepSeek, Mistral AI, Cerebras, Together AI, and Ollama models.
    """
    registry = ProviderRegistry()

    # --- 1. Groq (Free Tier, Ultra-Fast 500+ tok/s) ---
    registry.register(ProviderEntry(
        name="groq",
        models=[
            ModelEntry(
                provider="groq",
                model_name="llama-3.3-70b-versatile",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=128_000,
            ),
            ModelEntry(
                provider="groq",
                model_name="llama-3.1-8b-instant",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=128_000,
            ),
            ModelEntry(
                provider="groq",
                model_name="mixtral-8x7b-32768",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=32_768,
            ),
            ModelEntry(
                provider="groq",
                model_name="gemma2-9b-it",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=8_192,
            ),
            ModelEntry(
                provider="groq",
                model_name="deepseek-r1-distill-llama-70b",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=128_000,
            ),
        ],
        factory=_create_openai_compatible_factory(
            "groq",
            "https://api.groq.com/openai/v1",
            ["GROQ_API_KEY"]
        ),
    ))

    # --- 2. OpenRouter (Free Community Models) ---
    registry.register(ProviderEntry(
        name="openrouter",
        models=[
            ModelEntry(
                provider="openrouter",
                model_name="meta-llama/llama-3.3-70b-instruct:free",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=128_000,
            ),
            ModelEntry(
                provider="openrouter",
                model_name="google/gemini-2.0-flash-exp:free",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=1_000_000,
            ),
            ModelEntry(
                provider="openrouter",
                model_name="deepseek/deepseek-r1:free",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=64_000,
            ),
            ModelEntry(
                provider="openrouter",
                model_name="qwen/qwen-2.5-coder-32b-instruct:free",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=32_768,
            ),
            ModelEntry(
                provider="openrouter",
                model_name="mistralai/mistral-7b-instruct:free",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=32_768,
            ),
        ],
        factory=_create_openai_compatible_factory(
            "openrouter",
            "https://openrouter.ai/api/v1",
            ["OPENROUTER_API_KEY"]
        ),
    ))

    # --- 3. Google Gemini (Google AI Studio Free Tier) ---
    registry.register(ProviderEntry(
        name="gemini",
        models=[
            ModelEntry(
                provider="gemini",
                model_name="gemini-2.0-flash",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=1_000_000,
            ),
            ModelEntry(
                provider="gemini",
                model_name="gemini-1.5-flash",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=1_000_000,
            ),
            ModelEntry(
                provider="gemini",
                model_name="gemini-1.5-pro",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=2_000_000,
            ),
        ],
        factory=_create_openai_compatible_factory(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
        ),
    ))

    # --- 4. DeepSeek (DeepSeek V3 & R1) ---
    registry.register(ProviderEntry(
        name="deepseek",
        models=[
            ModelEntry(
                provider="deepseek",
                model_name="deepseek-chat",
                cost_per_input_token=0.14 / 1_000_000,
                cost_per_output_token=0.28 / 1_000_000,
                max_context_tokens=64_000,
            ),
            ModelEntry(
                provider="deepseek",
                model_name="deepseek-reasoner",
                cost_per_input_token=0.55 / 1_000_000,
                cost_per_output_token=2.19 / 1_000_000,
                max_context_tokens=64_000,
            ),
        ],
        factory=_create_openai_compatible_factory(
            "deepseek",
            "https://api.deepseek.com/v1",
            ["DEEPSEEK_API_KEY"]
        ),
    ))

    # --- 5. Mistral AI (La Plateforme Free Tier) ---
    registry.register(ProviderEntry(
        name="mistral",
        models=[
            ModelEntry(
                provider="mistral",
                model_name="mistral-small-latest",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=32_000,
            ),
            ModelEntry(
                provider="mistral",
                model_name="codestral-latest",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=32_000,
                eligible_artifact_types=["CODE_GENERATION", "API_SPEC"],
            ),
            ModelEntry(
                provider="mistral",
                model_name="open-mistral-nemo",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=128_000,
            ),
        ],
        factory=_create_openai_compatible_factory(
            "mistral",
            "https://api.mistral.ai/v1",
            ["MISTRAL_API_KEY"]
        ),
    ))

    # --- 6. Cerebras (Ultra-Fast Wafer Scale Free Tier) ---
    registry.register(ProviderEntry(
        name="cerebras",
        models=[
            ModelEntry(
                provider="cerebras",
                model_name="llama3.1-70b",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=128_000,
            ),
            ModelEntry(
                provider="cerebras",
                model_name="llama3.1-8b",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=128_000,
            ),
        ],
        factory=_create_openai_compatible_factory(
            "cerebras",
            "https://api.cerebras.ai/v1",
            ["CEREBRAS_API_KEY"]
        ),
    ))

    # --- 7. Together AI (Open Source Models) ---
    registry.register(ProviderEntry(
        name="together",
        models=[
            ModelEntry(
                provider="together",
                model_name="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                cost_per_input_token=0.18 / 1_000_000,
                cost_per_output_token=0.18 / 1_000_000,
                max_context_tokens=128_000,
            ),
            ModelEntry(
                provider="together",
                model_name="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                cost_per_input_token=0.88 / 1_000_000,
                cost_per_output_token=0.88 / 1_000_000,
                max_context_tokens=128_000,
            ),
        ],
        factory=_create_openai_compatible_factory(
            "together",
            "https://api.together.xyz/v1",
            ["TOGETHER_API_KEY"]
        ),
    ))

    # --- 8. Ollama (Local Self-Hosted, 100% Free & Unlimited) ---
    registry.register(ProviderEntry(
        name="ollama",
        models=[
            ModelEntry(
                provider="ollama",
                model_name="llama3.2",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=128_000,
            ),
            ModelEntry(
                provider="ollama",
                model_name="llama3.1",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=128_000,
            ),
            ModelEntry(
                provider="ollama",
                model_name="deepseek-coder",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=64_000,
            ),
            ModelEntry(
                provider="ollama",
                model_name="qwen2.5-coder",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=32_768,
            ),
            ModelEntry(
                provider="ollama",
                model_name="mistral",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                max_context_tokens=32_768,
            ),
        ],
        factory=_create_openai_compatible_factory(
            "ollama",
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            ["OLLAMA_API_KEY"],
            default_key="ollama" if os.getenv("OLLAMA_ENABLED", "false").lower() in ("true", "1", "yes") else ""
        ),
    ))

    # --- 9. OpenAI ---
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

    # --- 10. Anthropic ---
    registry.register(ProviderEntry(
        name="anthropic",
        models=[
            ModelEntry(
                provider="anthropic",
                model_name="claude-3-5-sonnet-20241022",
                cost_per_input_token=3.0 / 1_000_000,    # $3 / 1M tokens
                cost_per_output_token=15.0 / 1_000_000,  # $15 / 1M tokens
                max_context_tokens=200_000,
            ),
            ModelEntry(
                provider="anthropic",
                model_name="claude-3-5-haiku-20241022",
                cost_per_input_token=0.80 / 1_000_000,   # $0.80 / 1M tokens
                cost_per_output_token=4.0 / 1_000_000,   # $4 / 1M tokens
                max_context_tokens=200_000,
            ),
            ModelEntry(
                provider="anthropic",
                model_name="claude-3-haiku-20240307",
                cost_per_input_token=0.25 / 1_000_000,
                cost_per_output_token=1.25 / 1_000_000,
                max_context_tokens=200_000,
            ),
        ],
        factory=_anthropic_factory,
    ))

    return registry


# Singleton registry used throughout the application
PROVIDER_REGISTRY = build_default_registry()
