"""LLM設定取得ヘルパー."""

import os
from dataclasses import dataclass

from .exceptions import LLMConfigurationError


@dataclass
class LLMSettings:
    """LiteLLM Proxy経由のLLM設定を保持するデータクラス."""

    proxy_base_url: str
    proxy_api_key: str
    model_alias: str
    timeout: int
    service_name: str
    environment: str


def get_llm_settings(service_name: str) -> LLMSettings:
    """サービス名に対応するLLM設定を取得する.

    Args:
        service_name: サービス識別名（orchestrator, detective, talk）

    Returns:
        LLMSettings: LiteLLM Proxy接続用の設定

    Raises:
        LLMConfigurationError: 設定が存在しない場合
    """
    from .models import LLMServiceConfig

    try:
        config = LLMServiceConfig.objects.select_related("provider_config").get(
            service_name=service_name, is_active=True
        )
    except LLMServiceConfig.DoesNotExist as err:
        raise LLMConfigurationError(
            f"サービス '{service_name}' のLLM設定がありません。\n"
            "Django管理画面からLLMサービス設定を作成してください。"
        ) from err

    provider = config.provider_config
    proxy_base_url = os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000/v1")
    # プロバイダー設定のVirtual Keyを優先、未設定時はマスターキーにフォールバック
    proxy_api_key = provider.proxy_api_key or os.getenv("LITELLM_MASTER_KEY", "")
    environment = os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "default")

    return LLMSettings(
        proxy_base_url=proxy_base_url,
        proxy_api_key=proxy_api_key,
        model_alias=provider.model_alias,
        timeout=config.timeout,
        service_name=service_name,
        environment=environment,
    )
