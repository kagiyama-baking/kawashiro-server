"""Tavily設定取得ヘルパー."""

from dataclasses import dataclass

from .exceptions import TavilyConfigurationError


@dataclass
class TavilySettings:
    """Tavily API設定を保持するデータクラス."""

    api_key: str
    timeout: int


def get_tavily_settings() -> TavilySettings:
    """データベースから有効なTavily API設定を取得.

    Returns:
        TavilySettings: 設定データクラス

    Raises:
        TavilyConfigurationError: 有効な設定が存在しないか、APIキーが空の場合
    """
    from .models import TavilyConfig

    try:
        config = TavilyConfig.objects.get_active_config()
    except TavilyConfig.DoesNotExist as err:
        raise TavilyConfigurationError(
            "有効なTavily API設定がありません。\n"
            "Django管理画面から設定を作成し、有効にしてください。"
        ) from err

    if not config.api_key:
        raise TavilyConfigurationError(
            f"設定「{config.name}」のAPIキーが未入力です。\n"
            "Django管理画面から設定を行ってください。"
        )

    return TavilySettings(
        api_key=config.api_key,
        timeout=config.timeout,
    )
