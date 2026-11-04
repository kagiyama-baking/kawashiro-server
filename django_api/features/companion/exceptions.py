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


class CompanionNotConfiguredError(CompanionError):
    """有効な Companion 設定を 1 件に決められない（ないか、複数ある）.

    Attributes:
        multiple: 有効な設定が複数ある（False なら 1 件もない）
    """

    def __init__(self, *, multiple: bool = False):
        super().__init__(
            "有効な Companion 設定が複数あります（管理画面で 1 件だけを有効にし直してください）"
            if multiple
            else "有効な Companion 設定がありません（管理画面で設定を有効にしてください）"
        )
        self.multiple = multiple


class UnknownSkillError(CompanionError):
    """指定したスキルが、有効な設定に登録されていないか、無効.

    Attributes:
        skill_name: 指定されたスキル名
    """

    def __init__(self, skill_name: str):
        super().__init__(f"スキル「{skill_name}」は登録されていないか、無効です")
        self.skill_name = skill_name
