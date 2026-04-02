"""LLM設定取得ヘルパー"""

from dataclasses import dataclass

from .exceptions import OpenAIConfigurationError


@dataclass
class OpenAISettings:
    """OpenAI API設定を保持するデータクラス"""

    api_key: str
    model: str
    embedding_model: str
    timeout: int


def get_openai_settings() -> OpenAISettings:
    """
    データベースから有効なOpenAI API設定を取得する

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
