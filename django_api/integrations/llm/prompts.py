"""プロンプト（Prompts の Prompt）の本文の取得（全エージェント共通）."""

from typing import Any

from integrations.langfuse.client import fetch_text_prompt
from integrations.langfuse.exceptions import LangfusePromptError, PromptUnavailableError

from .models import Prompt


def resolve_prompt_text(prompt: Prompt, /, **variables: Any) -> str:
    """プロンプトの本文を Langfuse から取り、取れないか空なら例外にする.

    プロンプト名と同じ名前の Langfuse の text プロンプトを、プロンプトのラベルで取る
    （フォールバックはない）。変数を渡すと、本文の `{{変数}}` に差し込む（値は str にし、
    渡していない変数の `{{x}}` は残る）。渡さなければ展開しない。SDK のキャッシュ（既定
    60 秒。取り直しに失敗したら期限切れの本文を返す）はそのまま使う。Langfuse と通信する
    同期関数なので、イベントループの外で呼ぶ。

    Args:
        prompt: 本文を取るプロンプト
        **variables: 本文に差し込む変数（HN Agent の user プロンプトのスレッドの情報など）

    Returns:
        前後の空白を除いた本文

    Raises:
        PromptUnavailableError: 取れない場合（元の LangfusePromptError を `__cause__` に
            持つ）か、本文が空（空白だけ）の場合
    """
    try:
        text = fetch_text_prompt(
            prompt.name, label=prompt.label, variables=variables or None
        )
    except LangfusePromptError as exc:
        raise PromptUnavailableError(prompt.name, reason=str(exc)) from exc
    text = text.strip()
    if not text:
        raise PromptUnavailableError(prompt.name, reason="本文が空です")
    return text
