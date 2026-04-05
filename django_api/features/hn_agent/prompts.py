"""Langfuseプロンプト取得ヘルパー."""

import logging

logger = logging.getLogger(__name__)


def get_prompt(name: str, fallback: str) -> str:
    """Langfuseからプロンプトを取得.

    Langfuse到達不可時やプロンプト未登録時はフォールバック値を返す。

    Args:
        name: Langfuse上のプロンプト名
        fallback: フォールバック値（ハードコード定数）

    Returns:
        プロンプト文字列
    """
    try:
        from langfuse import get_client

        client = get_client()
        prompt = client.get_prompt(name)
        compiled = prompt.compile()
        logger.debug("Langfuseプロンプト取得: %s", name)
        return compiled
    except ImportError:
        logger.debug("langfuseが未インストール、フォールバック使用: %s", name)
        return fallback
    except Exception:
        logger.warning(
            "Langfuseプロンプト取得失敗、フォールバック使用: %s",
            name,
            exc_info=True,
        )
        return fallback
