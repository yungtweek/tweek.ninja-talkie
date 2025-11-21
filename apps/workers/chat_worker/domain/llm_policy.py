from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence


class LlmProvider(str, Enum):
    """Types of supported LLM providers.

    Domain layer only knows *who* provides the model.
    Transport details (gRPC / HTTP / SDK) are handled in infrastructure.
    """
    VLLM = "vllm"
    OPENAI = "openai"


@dataclass(frozen=True)
class FallbackDecision:
    """Represents the provider order to attempt for an LLM call.

    - primary: provider to try first
    - fallbacks: providers to try sequentially if primary fails
    """
    primary: LlmProvider
    fallbacks: Sequence[LlmProvider]

    @property
    def ordered_providers(self) -> List[LlmProvider]:
        """Return the provider list in order: primary first, then fallbacks (deduplicated)."""
        seen: set[LlmProvider] = set()
        ordered: List[LlmProvider] = []

        def _add(p: LlmProvider) -> None:
            if p not in seen:
                seen.add(p)
                ordered.append(p)

        _add(self.primary)
        for fb in self.fallbacks:
            _add(fb)

        return ordered


def parse_providers(value: str) -> List[LlmProvider]:
    """Parse a comma‑separated provider string into a list of LlmProvider values.

    Example:
        "vllm,openai" -> [LlmProvider.VLLM, LlmProvider.OPENAI]
        " openai "    -> [LlmProvider.OPENAI]
    """
    providers: List[LlmProvider] = []

    for raw in value.split(","):
        name = raw.strip()
        if not name:
            continue
        try:
            providers.append(LlmProvider(name))
        except ValueError:
            # Ignore unknown provider names (can be tightened by domain rules if needed)
            continue

    return providers


# Default domain-level policy (can be overridden via environment/settings)
DEFAULT_PRIMARY_PROVIDER = LlmProvider.VLLM
DEFAULT_FALLBACK_PROVIDERS: Sequence[LlmProvider] = (LlmProvider.OPENAI,)


def get_default_policy(chat_mode: Optional[str] = None) -> FallbackDecision:
    """Return the default fallback policy.

    chat_mode is reserved for future expansion, e.g.:

        - gen mode: vLLM -> OpenAI
        - rag mode: OpenAI -> vLLM
        - system mode: vLLM only
    """
    # TODO: chat_mode 기반으로 정책 분기 필요하면 여기서 구현
    return FallbackDecision(
        primary=DEFAULT_PRIMARY_PROVIDER,
        fallbacks=list(DEFAULT_FALLBACK_PROVIDERS),
    )


def build_policy_from_config(
        primary: str,
        fallbacks: Optional[str] = None,
) -> FallbackDecision:
    """Construct a fallback policy from configuration strings.

    Example:
        primary="vllm"
        fallbacks="openai"

    The domain layer only consumes LlmProvider and FallbackDecision objects.
    """
    try:
        primary_provider = LlmProvider(primary.strip())
    except ValueError:
        # Fallback to default provider (can be changed to raise if stricter behavior is needed)
        primary_provider = DEFAULT_PRIMARY_PROVIDER

    fallback_providers: List[LlmProvider] = []
    if fallbacks:
        fallback_providers = parse_providers(fallbacks)

    # Deduplicate primary from fallback list
    decision = FallbackDecision(
        primary=primary_provider,
        fallbacks=fallback_providers,
    )
    return decision