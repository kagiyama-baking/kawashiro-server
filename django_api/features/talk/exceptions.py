"""会話生成アプリの例外."""


class TalkError(Exception):
    """Talk 機能の基底例外."""


class PlaceholderDataMissingError(TalkError):
    """プロンプト中のプレースホルダーに必要な設定データが不足している."""
