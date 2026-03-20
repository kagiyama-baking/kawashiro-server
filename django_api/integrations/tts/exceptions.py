"""TTS例外クラス."""


class TTSError(Exception):
    """TTS関連の基底例外."""


class TTSTimeoutError(TTSError):
    """TTSサービスタイムアウトエラー."""


class TTSNetworkError(TTSError):
    """TTSサービスネットワークエラー."""
