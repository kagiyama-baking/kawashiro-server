"""Agent Skills（AgentSkill）の本文の取得（全エージェント共通）."""

from integrations.langfuse.client import fetch_text_prompt
from integrations.langfuse.exceptions import LangfusePromptError, PromptUnavailableError

from .models import AgentSkill


def resolve_skill_body(skill: AgentSkill) -> str:
    """スキルの本文を Langfuse から取り、取れないか空なら例外にする.

    スキル名と同じ名前の Langfuse の text プロンプトを、スキルのラベルで取る。フォールバックは
    ない。変数は展開しない。SDK のキャッシュ（既定 60 秒。取り直しに失敗したら期限切れの
    本文を返す）はそのまま使う。
    Langfuse と通信する同期関数なので、イベントループの外で呼ぶ。

    Args:
        skill: 本文を取るスキル

    Returns:
        前後の空白を除いた本文

    Raises:
        PromptUnavailableError: 取れない場合（元の LangfusePromptError を `__cause__` に
            持つ）か、本文が空（空白だけ）の場合
    """
    try:
        text = fetch_text_prompt(skill.name, label=skill.label)
    except LangfusePromptError as exc:
        raise PromptUnavailableError(skill.name, reason=str(exc)) from exc
    text = text.strip()
    if not text:
        raise PromptUnavailableError(skill.name, reason="本文が空です")
    return text
