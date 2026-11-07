"""Companion の例外."""


class CompanionError(Exception):
    """Companion の基底例外."""


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
    """指定したスキルが、有効な設定で選ばれていないか、無効.

    Agent Skills に登録がない・登録はあるが有効な設定で選んでいない・無効のどれか。

    Attributes:
        skill_name: 指定されたスキル名
    """

    def __init__(self, skill_name: str):
        super().__init__(
            f"スキル「{skill_name}」は有効な Companion 設定で選ばれていないか、無効です"
        )
        self.skill_name = skill_name
