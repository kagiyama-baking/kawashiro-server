"""Langfuse のプロンプトの取得の代役."""

from langfuse.api import NotFoundError
from langfuse.model import Prompt_Text, TextPromptClient


class FakeLangfuse:
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
