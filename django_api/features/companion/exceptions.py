"""Companion の例外."""


class CompanionError(Exception):
    """Companion の基底例外."""


class PromptUnavailableError(CompanionError):
    """プロンプト（キャラクター設定・スキルの本文）の本文が空で、使えない.

    Langfuse から取れないときはフォールバックテキストに落ちるが、それも空のことがある。

    Attributes:
        ref_name: 本文が空だったプロンプト参照の識別名（`LangfusePromptRef.name`）
    """

    def __init__(self, ref_name: str):
        super().__init__(
            f"プロンプト「{ref_name}」の本文が空です"
            "（Langfuse のプロンプトとフォールバックテキストを確認してください）"
        )
        self.ref_name = ref_name
