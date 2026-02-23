"""OpenAI APIクライアント."""

from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI
from openai.types.chat import ChatCompletionMessage

from core.metrics import EXTERNAL_API_DURATION
from llm_config.config import get_openai_settings

from .exceptions import OpenAIAPIError, OpenAITimeoutError


class OpenAIClient:
    """OpenAI API クライアント."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        """クライアントを初期化.

        設定の優先順位:
        1. 引数で明示的に指定された値
        2. データベースの有効な設定

        Args:
            api_key: OpenAI APIキー。省略時はDB設定から取得
            model: 使用するモデル名。省略時はDB設定から取得
            timeout: タイムアウト秒数。省略時はDB設定から取得

        Raises:
            OpenAIConfigurationError: DB設定がない、または必須項目が未設定の場合
        """
        # DB設定を取得（設定がなければOpenAIConfigurationErrorが発生）
        db_settings = get_openai_settings()

        # 引数が指定されていればそちらを優先、なければDB設定を使用
        self.api_key = api_key or db_settings.api_key
        self.model = model or db_settings.model
        self.timeout = timeout or db_settings.timeout

        self._client = OpenAI(api_key=self.api_key, timeout=self.timeout)

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
            with EXTERNAL_API_DURATION.labels(
                service="openai", method="generate_text"
            ).time():
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

            with EXTERNAL_API_DURATION.labels(
                service="openai", method="chat_completion"
            ).time():
                response = self._client.chat.completions.create(**kwargs)
            return response.choices[0].message
        except APITimeoutError as e:
            raise OpenAITimeoutError(
                "OpenAI APIへのリクエストがタイムアウトしました"
            ) from e
        except APIConnectionError as e:
            raise OpenAIAPIError("OpenAI APIへの接続に失敗しました") from e
