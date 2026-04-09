"""LLM設定取得ヘルパー."""

import os
from dataclasses import dataclass

from .exceptions import LLMConfigurationError, OpenAIConfigurationError


@dataclass
class OpenAISettings:
    """OpenAI API設定を保持するデータクラス."""

    api_key: str
    model: str
    embedding_model: str
    timeout: int


@dataclass
class LLMSettings:
    """LiteLLM Proxy経由のLLM設定を保持するデータクラス."""

    proxy_base_url: str
    proxy_api_key: str
    model_alias: str
    timeout: int


def get_openai_settings() -> OpenAISettings:
    """データベースから有効なOpenAI API設定を取得する.

    Returns:
        OpenAISettings: 設定データクラス

    Raises:
        OpenAIConfigurationError: 有効な設定が存在しないか、必須フィールドが空の場合
    """
    from .models import OpenAIConfig

    try:
        config = OpenAIConfig.objects.get_active_config()
    except OpenAIConfig.DoesNotExist as err:
        raise OpenAIConfigurationError(
            "有効なOpenAI API設定がありません。\n"
            "Django管理画面から設定を作成し、有効にしてください。"
        ) from err

    # 必須フィールドのバリデーション
    missing_fields = []
    if not config.api_key:
        missing_fields.append("APIキー")
    if not config.model:
        missing_fields.append("モデル")

    if missing_fields:
        raise OpenAIConfigurationError(
            f"設定「{config.name}」の以下の項目が未入力です: {', '.join(missing_fields)}\n"
            "Django管理画面から設定を行ってください。"
        )

    return OpenAISettings(
        api_key=config.api_key,
        model=config.model,
        embedding_model=config.embedding_model,
        timeout=config.timeout,
    )


def get_llm_settings(service_name: str) -> LLMSettings:
    """サービス名に対応するLLM設定を取得する.

    Args:
        service_name: サービス識別名（orchestrator, detective, talk, embedding）

    Returns:
        LLMSettings: LiteLLM Proxy接続用の設定

    Raises:
        LLMConfigurationError: 設定が存在しない場合
    """
    from .models import LLMServiceConfig

    try:
        config = LLMServiceConfig.objects.get(service_name=service_name, is_active=True)
    except LLMServiceConfig.DoesNotExist as err:
        raise LLMConfigurationError(
            f"サービス '{service_name}' のLLM設定がありません。\n"
            "Django管理画面からLLMサービス設定を作成してください。"
        ) from err

    proxy_base_url = os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000/v1")
    proxy_api_key = os.getenv("LITELLM_MASTER_KEY", "")

    return LLMSettings(
        proxy_base_url=proxy_base_url,
        proxy_api_key=proxy_api_key,
        model_alias=config.model_alias,
        timeout=config.timeout,
    )
