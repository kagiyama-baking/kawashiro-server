"""integrations.llm.prompts のテスト（プロンプトの本文を Langfuse から取る。フォールバックはない）.

Langfuse は代役（`langfuse_prompts`。tests/conftest.py）にし、(プロンプト名, ラベル) で
入れた本文だけを返させる。
"""

from unittest.mock import patch

import pytest
from langfuse.model import ChatPromptClient, Prompt_Chat

from integrations.langfuse.exceptions import LangfusePromptError, PromptUnavailableError
from integrations.llm.models import Prompt
from integrations.llm.prompts import resolve_prompt_text

PROMPT_NAME = "hn-agent-detective-user"
EMPTY_TEXTS = ["", " \n\t "]


def _prompt(**fields) -> Prompt:
    """保存しないプロンプト（指定しなければ名前は PROMPT_NAME、ラベルは staging）."""
    return Prompt(**{"name": PROMPT_NAME, "label": "staging", **fields})


@pytest.mark.unit
class TestResolvePromptText:
    """resolve_prompt_text（プロンプト名とラベルで本文を取り、変数を差し込む）."""

    def test_resolve_prompt_text_returns_stripped_body_of_prompt_with_its_label(
        self, langfuse_prompts
    ):
        """プロンプト名と同じ名前の Langfuse のプロンプトをラベルで取り、前後の空白を除いて返す."""
        langfuse_prompts[(PROMPT_NAME, "staging")] = "\n  staging の本文\n"
        langfuse_prompts[(PROMPT_NAME, "production")] = "production の本文"

        assert resolve_prompt_text(_prompt()) == "staging の本文"

    def test_resolve_prompt_text_without_variables_keeps_placeholders(
        self, langfuse_prompts
    ):
        """変数を渡さなければ展開しない（`{{x}}` はそのまま届く）."""
        langfuse_prompts[(PROMPT_NAME, "staging")] = "現在時刻: {{datetime}}"

        assert resolve_prompt_text(_prompt()) == "現在時刻: {{datetime}}"

    def test_resolve_prompt_text_with_variables_expands_them(self, langfuse_prompts):
        """変数を渡すと本文の `{{x}}` に差し込む（`prompt` という名前の変数も渡せる）."""
        langfuse_prompts[(PROMPT_NAME, "staging")] = "{{title}} / {{prompt}}"

        text = resolve_prompt_text(_prompt(), title="記事", prompt="発話")

        assert text == "記事 / 発話"

    def test_resolve_prompt_text_with_variables_keeps_unknown_placeholders(
        self, langfuse_prompts
    ):
        """渡していない変数の `{{x}}` は残す."""
        langfuse_prompts[(PROMPT_NAME, "staging")] = "{{title}} / {{unknown}}"

        assert resolve_prompt_text(_prompt(), title="記事") == "記事 / {{unknown}}"

    def test_resolve_prompt_text_passes_name_label_and_variables_to_fetch(self):
        """Langfuse からはプロンプト名とラベルで取り、変数はそのまま渡す（なければ None）."""
        with patch(
            "integrations.llm.prompts.fetch_text_prompt", return_value="本文"
        ) as fetch:
            resolve_prompt_text(_prompt())
            resolve_prompt_text(_prompt(label="production"), title="記事")

        assert fetch.call_args_list[0].args == (PROMPT_NAME,)
        assert fetch.call_args_list[0].kwargs == {"label": "staging", "variables": None}
        assert fetch.call_args_list[1].kwargs == {
            "label": "production",
            "variables": {"title": "記事"},
        }

    @pytest.mark.parametrize("body", EMPTY_TEXTS)
    def test_resolve_prompt_text_with_empty_body_raises_error_with_prompt_name(
        self, langfuse_prompts, body
    ):
        """本文が空（空白だけ）なら、プロンプト名を持つ PromptUnavailableError を送出する."""
        langfuse_prompts[(PROMPT_NAME, "staging")] = body

        with pytest.raises(PromptUnavailableError) as exc_info:
            resolve_prompt_text(_prompt())

        assert (exc_info.value.prompt_name, exc_info.value.reason) == (
            PROMPT_NAME,
            "本文が空です",
        )

    def test_resolve_prompt_text_without_prompt_for_label_raises_error_with_cause(
        self, langfuse_prompts
    ):
        """そのラベルのプロンプトがなければ PromptUnavailableError（ほかのラベルは使わない）.

        取得の失敗（LangfusePromptError）はそのまま出さず、原因（`__cause__`）として持つ。
        """
        langfuse_prompts[(PROMPT_NAME, "production")] = "production の本文"

        with pytest.raises(PromptUnavailableError, match=PROMPT_NAME) as exc_info:
            resolve_prompt_text(_prompt())

        cause = exc_info.value.__cause__
        assert isinstance(cause, LangfusePromptError)
        assert exc_info.value.prompt_name == PROMPT_NAME
        assert exc_info.value.reason == str(cause)

    def test_resolve_prompt_text_when_langfuse_unreachable_raises_error_with_cause(
        self, langfuse_unreachable
    ):
        """Langfuse に届かなければ PromptUnavailableError（理由に取得の失敗を書く）."""
        with pytest.raises(PromptUnavailableError) as exc_info:
            resolve_prompt_text(_prompt())

        assert isinstance(exc_info.value.__cause__, LangfusePromptError)
        assert exc_info.value.prompt_name == PROMPT_NAME

    def test_resolve_prompt_text_with_chat_prompt_raises_error_with_cause(self):
        """Langfuse のプロンプトが Chat 型なら PromptUnavailableError（Text 型だけを使う）."""
        chat = ChatPromptClient(
            Prompt_Chat(
                name=PROMPT_NAME,
                prompt=[{"role": "system", "content": "本文"}],
                version=1,
                config={},
                labels=["staging"],
                tags=[],
                type="chat",
            )
        )
        with patch("langfuse.get_client") as get_client:
            get_client.return_value.get_prompt.return_value = chat

            with pytest.raises(PromptUnavailableError) as exc_info:
                resolve_prompt_text(_prompt())

        assert isinstance(exc_info.value.__cause__, LangfusePromptError)
        assert "Text 型ではない" in exc_info.value.reason
