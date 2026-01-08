"""OpenAI APIクライアント."""

import os
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI
from openai.types.chat import ChatCompletionMessage

from .exceptions import OpenAIAPIError, OpenAIConfigurationError, OpenAITimeoutError

DEFAULT_MODEL = "gpt-5.2-chat-latest"
DEFAULT_TIMEOUT = 60


class OpenAIClient:
    """OpenAI API クライアント."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """クライアントを初期化.

        Args:
            api_key: OpenAI APIキー。省略時は環境変数OPENAI_API_KEYから取得
            model: 使用するモデル名
            timeout: タイムアウト秒数
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise OpenAIConfigurationError(
                "OPENAI_API_KEY environment variable is not set. "
                "Please set OPENAI_API_KEY in your .env file."
            )
        self.model = model
        self.timeout = timeout
        self._client = OpenAI(api_key=self.api_key, timeout=timeout)

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        """シンプルなテキスト生成.

        Args:
            prompt: ユーザーメッセージ
            system_prompt: システムプロンプト（オプション）

        Returns:
            生成されたテキスト

        Raises:
            OpenAITimeoutError: タイムアウト時
            OpenAIAPIError: API呼び出しエラー時
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
            )
            return response.choices[0].message.content or ""
        except APITimeoutError as e:
            raise OpenAITimeoutError(
                "OpenAI APIへのリクエストがタイムアウトしました"
            ) from e
        except APIConnectionError as e:
            raise OpenAIAPIError("OpenAI APIへの接続に失敗しました") from e

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> ChatCompletionMessage:
        """チャット補完を実行（Function Calling対応）.

        Args:
            messages: メッセージリスト
            tools: ツール定義リスト
            tool_choice: ツール選択モード（"auto", "none", "required"）

        Returns:
            ChatCompletionMessage: レスポンスメッセージ

        Raises:
            OpenAITimeoutError: タイムアウト時
            OpenAIAPIError: API呼び出しエラー時
        """
        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice

            response = self._client.chat.completions.create(**kwargs)
            return response.choices[0].message
        except APITimeoutError as e:
            raise OpenAITimeoutError(
                "OpenAI APIへのリクエストがタイムアウトしました"
            ) from e
        except APIConnectionError as e:
            raise OpenAIAPIError("OpenAI APIへの接続に失敗しました") from e
