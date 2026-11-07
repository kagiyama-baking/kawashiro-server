"""Langfuse関連の例外."""


class LangfusePromptError(Exception):
    """Langfuseプロンプト取得・コンパイルに関するエラー."""


class PromptUnavailableError(Exception):
    """プロンプト（システムプロンプト・スキルの本文）を使えない.

    システムプロンプトは Langfuse から取れないとフォールバックテキストに落ちるので、使えない
    のは本文が空のときだけ。スキルの本文にはフォールバックがないので、Langfuse から取れない
    ときも使えない（`reason` に取得の失敗を書き、元の例外を `__cause__` に持つ）。

    Attributes:
        ref_name: 使えなかったプロンプトの名前（システムプロンプトは参照の識別名
            `LangfusePromptRef.name`、スキルの本文は Langfuse のプロンプト名。スキル名と同じ）
        reason: 使えなかった理由（本文が空・取得の失敗）
    """

    def __init__(self, ref_name: str, *, reason: str = "本文が空です"):
        super().__init__(f"プロンプト「{ref_name}」を使えません（{reason}）")
        self.ref_name = ref_name
        self.reason = reason
