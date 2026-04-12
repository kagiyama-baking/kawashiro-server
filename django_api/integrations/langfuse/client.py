"""Langfuseプロンプト解決ユーティリティ."""

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import LangfusePromptRef

logger = logging.getLogger(__name__)

_VARIABLE_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def resolve_prompt(ref: "LangfusePromptRef", **variables: Any) -> str:
    """LangfusePromptRef からプロンプト文字列を解決する.

    1. Langfuse から ref.langfuse_prompt_name / ref.label でプロンプトを取得し、
       compile(**variables) で変数を置換する。
    2. 取得失敗・未インストール時は ref.fallback_text を返し、
       variables による `{{key}}` の簡易置換を行う。

    Args:
        ref: プロンプト参照
        **variables: テンプレート変数（値は str() 可能であること）

    Returns:
        解決済みプロンプト文字列
    """
    try:
        from langfuse import get_client

        client = get_client()
        prompt = client.get_prompt(ref.langfuse_prompt_name, label=ref.label)
        compiled = prompt.compile(**variables)
        logger.debug("Langfuseプロンプト取得成功: %s", ref.name)
        return compiled
    except ImportError:
        logger.debug("langfuse 未インストール、fallback使用: %s", ref.name)
        return _render_fallback(ref.fallback_text, variables)
    except Exception:
        logger.warning(
            "Langfuseプロンプト取得失敗、fallback使用: %s",
            ref.name,
            exc_info=True,
        )
        return _render_fallback(ref.fallback_text, variables)


def _render_fallback(template: str, variables: dict[str, Any]) -> str:
    """フォールバックテキストに variables を簡易置換する.

    `{{key}}` を variables[key] で str 置換する Mustache 風簡易レンダラ。
    未知のキーは元の `{{key}}` のまま残す。
    """
    if not variables:
        return template

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        return match.group(0)

    return _VARIABLE_PATTERN.sub(_replace, template)
