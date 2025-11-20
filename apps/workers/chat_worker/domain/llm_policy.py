from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence


class LlmProvider(str, Enum):
    """사용 가능한 LLM 제공자 종류.

    도메인 레벨에선 '누가 제공하는지'만 알고,
    실제 호출 방식(gRPC / HTTP / OpenAI SDK 등)은 모른다.
    """
    VLLM = "vllm"
    OPENAI = "openai"


@dataclass(frozen=True)
class FallbackDecision:
    """LLM 호출 시 어떤 제공자를 어떤 순서로 사용할지에 대한 결정.

    - primary: 먼저 시도할 provider
    - fallbacks: primary 실패 시 순서대로 시도할 provider 리스트
    """
    primary: LlmProvider
    fallbacks: Sequence[LlmProvider]

    @property
    def ordered_providers(self) -> List[LlmProvider]:
        """primary + fallbacks 를 순서대로 합친 리스트."""
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
    """쉼표로 구분된 provider 문자열을 LlmProvider 리스트로 변환.

    예:
        "vllm,openai"  -> [LlmProvider.VLLM, LlmProvider.OPENAI]
        " openai "     -> [LlmProvider.OPENAI]
    """
    providers: List[LlmProvider] = []

    for raw in value.split(","):
        name = raw.strip()
        if not name:
            continue
        try:
            providers.append(LlmProvider(name))
        except ValueError:
            # 알 수 없는 provider 이름은 무시 (도메인 규칙에 맞게 필요 시 변경 가능)
            continue

    return providers


# 도메인 레벨에서 사용하는 기본 정책 (env / settings 로 덮어쓸 수 있음)
DEFAULT_PRIMARY_PROVIDER = LlmProvider.VLLM
DEFAULT_FALLBACK_PROVIDERS: Sequence[LlmProvider] = (LlmProvider.OPENAI,)


def get_default_policy(chat_mode: Optional[str] = None) -> FallbackDecision:
    """기본 LLM 폴백 정책을 반환.

    현재는 chat_mode 를 사용하지 않지만,
    나중에 다음과 같이 확장할 수 있다:

        - gen 모드: vLLM -> OpenAI
        - rag 모드: OpenAI -> vLLM
        - system 모드: vLLM only

    chat_mode:
        도메인에서 사용하는 채팅 모드 식별자 (예: "gen", "rag" 등)
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
    """환경설정에서 읽어온 provider 문자열을 기반으로 정책을 생성.

    예:
        primary="vllm"
        fallbacks="openai"

    같은 값을 Settings 에서 읽어와서 이 함수에 넘기면,
    도메인 레벨에서는 LlmProvider/ FallbackDecision 만 다루면 된다.
    """
    try:
        primary_provider = LlmProvider(primary.strip())
    except ValueError:
        # 잘못된 값이면 기본값 사용 (필요하면 에러로 바꾸기 가능)
        primary_provider = DEFAULT_PRIMARY_PROVIDER

    fallback_providers: List[LlmProvider] = []
    if fallbacks:
        fallback_providers = parse_providers(fallbacks)

    # primary 와 중복된 fallback 은 제거
    decision = FallbackDecision(
        primary=primary_provider,
        fallbacks=fallback_providers,
    )
    return decision