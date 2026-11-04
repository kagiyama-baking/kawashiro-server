"""Companion のテストの共通フィクスチャ（Langfuse のプロンプトの代役）."""

from unittest.mock import patch

import pytest
from langfuse.api import NotFoundError
from langfuse.model import Prompt_Text, TextPromptClient


class _FakeLangfuse:
    """`get_prompt` だけを持つ Langfuse のクライアントの代役（入れたプロンプトだけを返す）."""

    def __init__(self, prompts: dict[tuple[str, str], str]):
        self._prompts = prompts

    def get_prompt(
        self, name: str, *, label: str = "production", **_options
    ) -> TextPromptClient:
        """SDK と同じ Text 型のプロンプトを返す（ない名前・ラベルは SDK と同じ例外）."""
        try:
            body = self._prompts[(name, label)]
        except KeyError:
            raise NotFoundError(
                body={"message": f"Prompt not found: {name} (label={label})"}
            ) from None
        return TextPromptClient(
            Prompt_Text(
                name=name,
                prompt=body,
                version=1,
                config={},
                labels=[label],
                tags=[],
                type="text",
            )
        )


@pytest.fixture(autouse=True)
def langfuse_prompts():
    """Langfuse の text プロンプトの代役（`(プロンプト名, ラベル) → 本文` の dict）.

    autouse なので、companion のテストは Langfuse へ出ない。本文を返させたいテストは
    この fixture を引数に取り、dict に入れる。入れていない名前・ラベルは SDK と同じく
    NotFoundError で取得に失敗する（システムプロンプトは `resolve_prompt` が参照の
    フォールバックテキストに落とし、スキルの本文は PromptUnavailableError になる）。
    """
    prompts: dict[tuple[str, str], str] = {}
    with patch("langfuse.get_client", return_value=_FakeLangfuse(prompts)):
        yield prompts


@pytest.fixture
def langfuse_unreachable(langfuse_prompts):
    """Langfuse に届かない（クライアントを用意できない。入れた本文も返らない）."""
    with patch(
        "langfuse.get_client", side_effect=ConnectionError("Langfuse に届きません")
    ):
        yield
