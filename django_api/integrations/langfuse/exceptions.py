"""Langfuse関連の例外."""


class LangfusePromptError(Exception):
    """Langfuseプロンプト取得・コンパイルに関するエラー."""


class PromptUnavailableError(Exception):
    """プロンプト（Prompts のプロンプト・スキルの本文）を使えない.

    Langfuse から取れない（`reason` に取得の失敗を書き、元の例外を `__cause__` に持つ）か、
    本文が空（空白だけ）のとき。どちらにもフォールバックはない。

    Attributes:
        prompt_name: 使えなかったプロンプトの Langfuse のプロンプト名（Prompts の
            プロンプト名・スキル名と同じ）
        reason: 使えなかった理由（本文が空・取得の失敗）
    """

    def __init__(self, prompt_name: str, *, reason: str = "本文が空です"):
        super().__init__(f"プロンプト「{prompt_name}」を使えません（{reason}）")
        self.prompt_name = prompt_name
        self.reason = reason
